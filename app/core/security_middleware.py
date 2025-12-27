"""
Security Middleware
Handles authentication, authorization, and security event logging
"""
import logging
from typing import Optional, Callable
from fastapi import Request, HTTPException, status, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time

from app.core.auth import cognito_auth
from app.core.database import get_database
from app.services.user_service import UserService
from app.services.security_service import SecurityService, SecurityEventType
from app.services.security_monitoring_service import SecurityMonitoringService
from app.models.user import UserRole

logger = logging.getLogger(__name__)
security = HTTPBearer()


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for security monitoring and rate limiting"""
    
    def __init__(self, app, rate_limit_requests: int = 100, rate_limit_window: int = 60):
        super().__init__(app)
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_window = rate_limit_window
        self.request_counts = {}  # In production, use Redis for distributed rate limiting
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through security middleware"""
        start_time = time.time()
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        try:
            # Initialize database connection for security service
            db = await get_database()
            security_service = SecurityService(db) if db else None
            monitoring_service = SecurityMonitoringService(db) if db else None
            
            # Check if IP is suspicious (only if security service is available)
            if security_service and await security_service.is_ip_suspicious(client_ip):
                if monitoring_service:
                    await monitoring_service.log_security_event(
                        event_type="suspicious_ip_blocked",
                        ip_address=client_ip,
                        user_agent=request.headers.get("user-agent"),
                        event_details={"reason": "blocked_suspicious_ip"},
                        severity="high"
                    )
                else:
                    await security_service.log_security_event(
                        event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
                        ip_address=client_ip,
                        user_agent=request.headers.get("user-agent"),
                        details={"reason": "blocked_suspicious_ip"}
                    )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Access temporarily blocked due to suspicious activity"
                )
            
            # Rate limiting
            if self._is_rate_limited(client_ip):
                if monitoring_service:
                    await monitoring_service.log_security_event(
                        event_type="rate_limit_exceeded",
                        ip_address=client_ip,
                        user_agent=request.headers.get("user-agent"),
                        event_details={"requests_per_minute": self.rate_limit_requests},
                        severity="medium"
                    )
                elif security_service:
                    await security_service.log_security_event(
                        event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                        ip_address=client_ip,
                        user_agent=request.headers.get("user-agent"),
                        details={"requests_per_minute": self.rate_limit_requests}
                    )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded"
                )
            
            # Process request
            response = await call_next(request)
            
            # Log request processing time
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            # Continue processing even if security middleware fails
            response = await call_next(request)
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(process_time)
            return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for forwarded headers (when behind proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"
    
    def _is_rate_limited(self, client_ip: str) -> bool:
        """Check if client IP is rate limited"""
        current_time = time.time()
        window_start = current_time - self.rate_limit_window
        
        # Clean old entries
        if client_ip in self.request_counts:
            self.request_counts[client_ip] = [
                timestamp for timestamp in self.request_counts[client_ip]
                if timestamp > window_start
            ]
        else:
            self.request_counts[client_ip] = []
        
        # Check if rate limit exceeded
        if len(self.request_counts[client_ip]) >= self.rate_limit_requests:
            return True
        
        # Add current request
        self.request_counts[client_ip].append(current_time)
        return False


async def get_current_user(credentials: HTTPAuthorizationCredentials = security) -> dict:
    """
    Dependency to get current authenticated user
    """
    try:
        # Verify JWT token
        token_data = await cognito_auth.verify_token(credentials.credentials)
        
        # Get user profile from database
        db = await get_database()
        user_service = UserService(db)
        user_profile = await user_service.get_user_by_cognito_id(token_data['user_id'])
        
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        return {
            "user_id": user_profile.user_id,
            "email": user_profile.email,
            "username": user_profile.username,
            "role": user_profile.role,
            "profile": user_profile
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )


async def require_role(required_roles: list[UserRole]):
    """
    Dependency factory to require specific roles
    """
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_role = current_user["role"]
        
        if user_role not in required_roles:
            # Log unauthorized access attempt
            db = await get_database()
            security_service = SecurityService(db)
            await security_service.log_security_event(
                event_type=SecurityEventType.ROLE_ESCALATION_ATTEMPT,
                user_id=current_user["user_id"],
                details={
                    "user_role": user_role.value if hasattr(user_role, 'value') else str(user_role),
                    "required_roles": [role.value for role in required_roles]
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[role.value for role in required_roles]}"
            )
        
        return current_user
    
    return role_checker


async def require_permission(required_permission, resource_owner_id: Optional[str] = None):
    """
    Dependency factory to require specific permissions
    """
    async def permission_checker(current_user: dict = Depends(get_current_user)) -> dict:
        db = await get_database()
        security_service = SecurityService(db)
        
        # Check if user has required permission
        await security_service.enforce_feature_access(
            user_id=current_user["user_id"],
            user_role=current_user["role"],
            required_permission=required_permission,
            resource_owner_id=resource_owner_id
        )
        
        return current_user
    
    return permission_checker


class RoleBasedAccessControl:
    """Utility class for role-based access control decorators"""
    
    @staticmethod
    def require_student_or_above():
        """Require student role or higher"""
        async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
            user_role = current_user["role"]
            required_roles = [UserRole.STUDENT, UserRole.INSTRUCTOR, UserRole.ADMIN]
            
            if user_role not in required_roles:
                # Log unauthorized access attempt
                db = await get_database()
                security_service = SecurityService(db)
                await security_service.log_security_event(
                    event_type=SecurityEventType.ROLE_ESCALATION_ATTEMPT,
                    user_id=current_user["user_id"],
                    details={
                        "user_role": user_role.value if hasattr(user_role, 'value') else str(user_role),
                        "required_roles": [role.value for role in required_roles]
                    }
                )
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required roles: {[role.value for role in required_roles]}"
                )
            
            return current_user
        
        return role_checker
    
    @staticmethod
    def require_instructor_or_above():
        """Require instructor role or higher"""
        async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
            user_role = current_user["role"]
            required_roles = [UserRole.INSTRUCTOR, UserRole.ADMIN]
            
            if user_role not in required_roles:
                # Log unauthorized access attempt
                db = await get_database()
                security_service = SecurityService(db)
                await security_service.log_security_event(
                    event_type=SecurityEventType.ROLE_ESCALATION_ATTEMPT,
                    user_id=current_user["user_id"],
                    details={
                        "user_role": user_role.value if hasattr(user_role, 'value') else str(user_role),
                        "required_roles": [role.value for role in required_roles]
                    }
                )
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required roles: {[role.value for role in required_roles]}"
                )
            
            return current_user
        
        return role_checker
    
    @staticmethod
    def require_admin():
        """Require admin role"""
        async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
            user_role = current_user["role"]
            required_roles = [UserRole.ADMIN]
            
            if user_role not in required_roles:
                # Log unauthorized access attempt
                db = await get_database()
                security_service = SecurityService(db)
                await security_service.log_security_event(
                    event_type=SecurityEventType.ROLE_ESCALATION_ATTEMPT,
                    user_id=current_user["user_id"],
                    details={
                        "user_role": user_role.value if hasattr(user_role, 'value') else str(user_role),
                        "required_roles": [role.value for role in required_roles]
                    }
                )
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required roles: {[role.value for role in required_roles]}"
                )
            
            return current_user
        
        return role_checker


async def log_security_event_dependency(
    request: Request,
    event_type: SecurityEventType,
    user_id: Optional[str] = None,
    details: Optional[dict] = None
):
    """
    Dependency to log security events
    """
    try:
        db = await get_database()
        security_service = SecurityService(db)
        
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")
        
        await security_service.log_security_event(
            event_type=event_type,
            user_id=user_id,
            ip_address=client_ip,
            user_agent=user_agent,
            details=details
        )
        
    except Exception as e:
        logger.error(f"Error logging security event: {e}")


# Convenience functions for common security checks

async def ensure_own_data_access(current_user: dict, resource_owner_id: str) -> None:
    """
    Ensure user can only access their own data unless they have elevated privileges
    """
    user_role = current_user["role"]
    user_id = current_user["user_id"]
    
    # Allow access if user is accessing their own data
    if user_id == resource_owner_id:
        return
    
    # Allow access if user has elevated privileges
    if user_role in [UserRole.INSTRUCTOR, UserRole.ADMIN]:
        return
    
    # Log unauthorized access attempt
    db = await get_database()
    security_service = SecurityService(db)
    await security_service.log_security_event(
        event_type=SecurityEventType.DATA_ACCESS_VIOLATION,
        user_id=user_id,
        details={
            "attempted_access_to": resource_owner_id,
            "user_role": user_role.value if hasattr(user_role, 'value') else str(user_role)
        }
    )
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: can only access your own data"
    )


async def validate_data_privacy_request(
    current_user: dict,
    request_type: str,
    target_user_id: Optional[str] = None
) -> None:
    """
    Validate data privacy requests (export, deletion)
    """
    user_id = current_user["user_id"]
    user_role = current_user["role"]
    
    # Users can request their own data
    if not target_user_id or target_user_id == user_id:
        return
    
    # Only admins can request data for other users
    if user_role != UserRole.ADMIN:
        db = await get_database()
        security_service = SecurityService(db)
        await security_service.log_security_event(
            event_type=SecurityEventType.UNAUTHORIZED_ACCESS,
            user_id=user_id,
            details={
                "request_type": request_type,
                "target_user_id": target_user_id,
                "user_role": user_role.value if hasattr(user_role, 'value') else str(user_role)
            }
        )
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: can only request your own data"
        )


class RateLimiter:
    """Advanced rate limiter for external API endpoints"""
    
    def __init__(self, requests_per_minute: int = 60, burst_limit: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.request_counts = {}  # In production, use Redis
        self.burst_counts = {}
    
    async def check_rate_limit(self, identifier: str, endpoint: str = "default"):
        """Check rate limit for identifier and endpoint"""
        current_time = time.time()
        key = f"{identifier}:{endpoint}"
        
        # Check burst limit (last 10 seconds)
        burst_window_start = current_time - 10
        if key in self.burst_counts:
            self.burst_counts[key] = [
                timestamp for timestamp in self.burst_counts[key]
                if timestamp > burst_window_start
            ]
        else:
            self.burst_counts[key] = []
        
        if len(self.burst_counts[key]) >= self.burst_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Burst rate limit exceeded. Please slow down your requests.",
                headers={"Retry-After": "10"}
            )
        
        # Check per-minute limit
        minute_window_start = current_time - 60
        if key in self.request_counts:
            self.request_counts[key] = [
                timestamp for timestamp in self.request_counts[key]
                if timestamp > minute_window_start
            ]
        else:
            self.request_counts[key] = []
        
        if len(self.request_counts[key]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute.",
                headers={"Retry-After": "60"}
            )
        
        # Record request
        self.request_counts[key].append(current_time)
        self.burst_counts[key].append(current_time)


class APIKeyAuth:
    """API Key authentication for third-party services"""
    
    def __init__(self):
        # In production, these would be stored in a secure database
        self.valid_api_keys = {
            "test_key_123": {
                "name": "Test Integration",
                "permissions": ["read", "write"],
                "rate_limit": 1000,
                "created_at": time.time()
            }
        }
    
    def __call__(self, x_api_key: Optional[str] = Header(None)):
        """Validate API key from header"""
        if not x_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "ApiKey"}
            )
        
        if x_api_key not in self.valid_api_keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"}
            )
        
        return x_api_key
    
    def get_api_key_info(self, api_key: str) -> dict:
        """Get API key information"""
        return self.valid_api_keys.get(api_key, {})
    
    def generate_api_key(self, name: str, permissions: list) -> str:
        """Generate new API key"""
        import secrets
        api_key = f"ak_{secrets.token_urlsafe(32)}"
        self.valid_api_keys[api_key] = {
            "name": name,
            "permissions": permissions,
            "rate_limit": 1000,
            "created_at": time.time()
        }
        return api_key