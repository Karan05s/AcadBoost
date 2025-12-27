"""
Security Management Service
Handles role-based access control, security event logging, and data privacy controls
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException, status
from app.models.user import UserRole
from app.core.redis_client import cache_manager
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """Security event types for logging"""
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    FAILED_LOGIN = "failed_login"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    DATA_ACCESS_VIOLATION = "data_access_violation"
    ROLE_ESCALATION_ATTEMPT = "role_escalation_attempt"
    INVALID_TOKEN = "invalid_token"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    DATA_EXPORT_REQUEST = "data_export_request"
    DATA_DELETION_REQUEST = "data_deletion_request"


class FeaturePermission(Enum):
    """Feature permissions for role-based access control"""
    # Student permissions
    VIEW_OWN_DASHBOARD = "view_own_dashboard"
    VIEW_OWN_PERFORMANCE = "view_own_performance"
    VIEW_OWN_RECOMMENDATIONS = "view_own_recommendations"
    UPDATE_OWN_PROFILE = "update_own_profile"
    REQUEST_DATA_EXPORT = "request_data_export"
    REQUEST_DATA_DELETION = "request_data_deletion"
    
    # Instructor permissions
    VIEW_STUDENT_ANALYTICS = "view_student_analytics"
    VIEW_CLASS_PERFORMANCE = "view_class_performance"
    MANAGE_ASSIGNMENTS = "manage_assignments"
    VIEW_LEARNING_GAPS = "view_learning_gaps"
    GENERATE_REPORTS = "generate_reports"
    
    # Admin permissions
    MANAGE_USERS = "manage_users"
    VIEW_SYSTEM_ANALYTICS = "view_system_analytics"
    MANAGE_SECURITY_SETTINGS = "manage_security_settings"
    VIEW_SECURITY_LOGS = "view_security_logs"
    SYSTEM_CONFIGURATION = "system_configuration"


class SecurityService:
    """Service for security management and access control"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.security_events_collection = db.security_events
        self.user_sessions_collection = db.user_sessions
        
        # Role-based permissions mapping
        self.role_permissions = {
            UserRole.STUDENT: [
                FeaturePermission.VIEW_OWN_DASHBOARD,
                FeaturePermission.VIEW_OWN_PERFORMANCE,
                FeaturePermission.VIEW_OWN_RECOMMENDATIONS,
                FeaturePermission.UPDATE_OWN_PROFILE,
                FeaturePermission.REQUEST_DATA_EXPORT,
                FeaturePermission.REQUEST_DATA_DELETION,
            ],
            UserRole.INSTRUCTOR: [
                # Include all student permissions
                FeaturePermission.VIEW_OWN_DASHBOARD,
                FeaturePermission.VIEW_OWN_PERFORMANCE,
                FeaturePermission.VIEW_OWN_RECOMMENDATIONS,
                FeaturePermission.UPDATE_OWN_PROFILE,
                FeaturePermission.REQUEST_DATA_EXPORT,
                FeaturePermission.REQUEST_DATA_DELETION,
                # Additional instructor permissions
                FeaturePermission.VIEW_STUDENT_ANALYTICS,
                FeaturePermission.VIEW_CLASS_PERFORMANCE,
                FeaturePermission.MANAGE_ASSIGNMENTS,
                FeaturePermission.VIEW_LEARNING_GAPS,
                FeaturePermission.GENERATE_REPORTS,
            ],
            UserRole.ADMIN: [
                # Include all permissions
                permission for permission in FeaturePermission
            ]
        }
    
    async def check_feature_access(
        self, 
        user_id: str, 
        user_role: UserRole, 
        required_permission: FeaturePermission,
        resource_owner_id: Optional[str] = None
    ) -> bool:
        """
        Check if user has access to a specific feature
        
        Args:
            user_id: ID of the user requesting access
            user_role: Role of the user
            required_permission: Permission required for the feature
            resource_owner_id: ID of the resource owner (for data access checks)
        """
        try:
            # Get permissions for user role
            user_permissions = self.role_permissions.get(user_role, [])
            
            # Check if user has the required permission
            if required_permission not in user_permissions:
                await self.log_security_event(
                    event_type=SecurityEventType.UNAUTHORIZED_ACCESS,
                    user_id=user_id,
                    details={
                        "required_permission": required_permission.value,
                        "user_role": user_role.value,
                        "resource_owner_id": resource_owner_id
                    }
                )
                return False
            
            # For data access permissions, ensure user can only access their own data
            # unless they have elevated privileges
            if required_permission in [
                FeaturePermission.VIEW_OWN_DASHBOARD,
                FeaturePermission.VIEW_OWN_PERFORMANCE,
                FeaturePermission.VIEW_OWN_RECOMMENDATIONS,
                FeaturePermission.UPDATE_OWN_PROFILE
            ]:
                if resource_owner_id and resource_owner_id != user_id:
                    # Check if user has elevated privileges
                    if user_role not in [UserRole.INSTRUCTOR, UserRole.ADMIN]:
                        await self.log_security_event(
                            event_type=SecurityEventType.DATA_ACCESS_VIOLATION,
                            user_id=user_id,
                            details={
                                "attempted_access_to": resource_owner_id,
                                "permission": required_permission.value
                            }
                        )
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking feature access for user {user_id}: {e}")
            return False
    
    async def enforce_feature_access(
        self,
        user_id: str,
        user_role: UserRole,
        required_permission: FeaturePermission,
        resource_owner_id: Optional[str] = None
    ) -> None:
        """
        Enforce feature access and raise HTTPException if access denied
        """
        has_access = await self.check_feature_access(
            user_id, user_role, required_permission, resource_owner_id
        )
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: insufficient permissions for {required_permission.value}"
            )
    
    async def log_security_event(
        self,
        event_type: SecurityEventType,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log security events for monitoring and auditing"""
        try:
            security_event = {
                "event_type": event_type.value,
                "user_id": user_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "timestamp": datetime.utcnow(),
                "details": details or {},
                "severity": self._get_event_severity(event_type)
            }
            
            # Store in database
            await self.security_events_collection.insert_one(security_event)
            
            # Log to application logger
            logger.warning(
                f"Security Event: {event_type.value} - User: {user_id} - "
                f"IP: {ip_address} - Details: {details}"
            )
            
            # Check for suspicious patterns
            await self._check_suspicious_activity(user_id, event_type, ip_address)
            
        except Exception as e:
            logger.error(f"Error logging security event: {e}")
    
    def _get_event_severity(self, event_type: SecurityEventType) -> str:
        """Get severity level for security event"""
        high_severity_events = [
            SecurityEventType.UNAUTHORIZED_ACCESS,
            SecurityEventType.DATA_ACCESS_VIOLATION,
            SecurityEventType.ROLE_ESCALATION_ATTEMPT,
            SecurityEventType.SUSPICIOUS_ACTIVITY
        ]
        
        medium_severity_events = [
            SecurityEventType.FAILED_LOGIN,
            SecurityEventType.INVALID_TOKEN,
            SecurityEventType.RATE_LIMIT_EXCEEDED
        ]
        
        if event_type in high_severity_events:
            return "HIGH"
        elif event_type in medium_severity_events:
            return "MEDIUM"
        else:
            return "LOW"
    
    async def _check_suspicious_activity(
        self,
        user_id: Optional[str],
        event_type: SecurityEventType,
        ip_address: Optional[str]
    ) -> None:
        """Check for suspicious activity patterns"""
        try:
            if not user_id and not ip_address:
                return
            
            # Check for multiple failed login attempts
            if event_type == SecurityEventType.FAILED_LOGIN:
                await self._check_failed_login_pattern(user_id, ip_address)
            
            # Check for multiple unauthorized access attempts
            if event_type == SecurityEventType.UNAUTHORIZED_ACCESS:
                await self._check_unauthorized_access_pattern(user_id, ip_address)
            
        except Exception as e:
            logger.error(f"Error checking suspicious activity: {e}")
    
    async def _check_failed_login_pattern(
        self,
        user_id: Optional[str],
        ip_address: Optional[str]
    ) -> None:
        """Check for suspicious failed login patterns"""
        try:
            # Check last 15 minutes
            cutoff_time = datetime.utcnow() - timedelta(minutes=15)
            
            # Build query
            query = {
                "event_type": SecurityEventType.FAILED_LOGIN.value,
                "timestamp": {"$gte": cutoff_time}
            }
            
            if user_id:
                query["user_id"] = user_id
            elif ip_address:
                query["ip_address"] = ip_address
            
            # Count failed attempts
            failed_attempts = await self.security_events_collection.count_documents(query)
            
            # If more than 5 failed attempts, log suspicious activity
            if failed_attempts >= 5:
                await self.log_security_event(
                    event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
                    user_id=user_id,
                    ip_address=ip_address,
                    details={
                        "pattern": "multiple_failed_logins",
                        "attempts_count": failed_attempts,
                        "time_window": "15_minutes"
                    }
                )
                
                # Cache the suspicious IP/user for rate limiting
                if ip_address:
                    await cache_manager.set_cache(
                        f"suspicious_ip:{ip_address}",
                        {"blocked_until": (datetime.utcnow() + timedelta(hours=1)).isoformat()},
                        expire=3600
                    )
                
        except Exception as e:
            logger.error(f"Error checking failed login pattern: {e}")
    
    async def _check_unauthorized_access_pattern(
        self,
        user_id: Optional[str],
        ip_address: Optional[str]
    ) -> None:
        """Check for suspicious unauthorized access patterns"""
        try:
            # Check last 10 minutes
            cutoff_time = datetime.utcnow() - timedelta(minutes=10)
            
            query = {
                "event_type": SecurityEventType.UNAUTHORIZED_ACCESS.value,
                "timestamp": {"$gte": cutoff_time}
            }
            
            if user_id:
                query["user_id"] = user_id
            elif ip_address:
                query["ip_address"] = ip_address
            
            unauthorized_attempts = await self.security_events_collection.count_documents(query)
            
            # If more than 3 unauthorized attempts, log suspicious activity
            if unauthorized_attempts >= 3:
                await self.log_security_event(
                    event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
                    user_id=user_id,
                    ip_address=ip_address,
                    details={
                        "pattern": "multiple_unauthorized_access",
                        "attempts_count": unauthorized_attempts,
                        "time_window": "10_minutes"
                    }
                )
                
        except Exception as e:
            logger.error(f"Error checking unauthorized access pattern: {e}")
    
    async def is_ip_suspicious(self, ip_address: str) -> bool:
        """Check if IP address is marked as suspicious"""
        try:
            suspicious_data = await cache_manager.get_cache(f"suspicious_ip:{ip_address}")
            if suspicious_data:
                blocked_until = datetime.fromisoformat(suspicious_data["blocked_until"])
                return datetime.utcnow() < blocked_until
            return False
        except Exception as e:
            logger.error(f"Error checking suspicious IP {ip_address}: {e}")
            return False
    
    async def create_user_session(
        self,
        user_id: str,
        session_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        expires_at: Optional[datetime] = None
    ) -> None:
        """Create user session record"""
        try:
            if not expires_at:
                expires_at = datetime.utcnow() + timedelta(hours=24)
            
            session_data = {
                "user_id": user_id,
                "session_token": session_token,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "created_at": datetime.utcnow(),
                "expires_at": expires_at,
                "active": True,
                "last_activity": datetime.utcnow()
            }
            
            await self.user_sessions_collection.insert_one(session_data)
            
            # Cache session for quick lookup
            await cache_manager.set_cache(
                f"session:{session_token}",
                session_data,
                expire=int((expires_at - datetime.utcnow()).total_seconds())
            )
            
        except Exception as e:
            logger.error(f"Error creating user session: {e}")
    
    async def validate_user_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """Validate user session"""
        try:
            # Check cache first
            session_data = await cache_manager.get_cache(f"session:{session_token}")
            
            if not session_data:
                # Check database
                session_data = await self.user_sessions_collection.find_one({
                    "session_token": session_token,
                    "active": True,
                    "expires_at": {"$gt": datetime.utcnow()}
                })
            
            if session_data:
                # Update last activity
                await self.user_sessions_collection.update_one(
                    {"session_token": session_token},
                    {"$set": {"last_activity": datetime.utcnow()}}
                )
                
                return session_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error validating session: {e}")
            return None
    
    async def invalidate_user_session(self, session_token: str) -> bool:
        """Invalidate user session"""
        try:
            # Update database
            result = await self.user_sessions_collection.update_one(
                {"session_token": session_token},
                {"$set": {"active": False, "invalidated_at": datetime.utcnow()}}
            )
            
            # Remove from cache
            await cache_manager.delete_cache(f"session:{session_token}")
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error invalidating session: {e}")
            return False
    
    async def get_security_events(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[SecurityEventType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get security events for monitoring"""
        try:
            query = {}
            
            if user_id:
                query["user_id"] = user_id
            
            if event_type:
                query["event_type"] = event_type.value
            
            if start_date or end_date:
                date_query = {}
                if start_date:
                    date_query["$gte"] = start_date
                if end_date:
                    date_query["$lte"] = end_date
                query["timestamp"] = date_query
            
            cursor = self.security_events_collection.find(query).sort("timestamp", -1).limit(limit)
            events = await cursor.to_list(length=limit)
            
            return events
            
        except Exception as e:
            logger.error(f"Error getting security events: {e}")
            return []
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        try:
            result = await self.user_sessions_collection.delete_many({
                "expires_at": {"$lt": datetime.utcnow()}
            })
            
            logger.info(f"Cleaned up {result.deleted_count} expired sessions")
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0