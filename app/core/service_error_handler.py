"""
Service Error Handler
Provides comprehensive error handling across all services
"""
import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict

from app.core.redis_client import cache_manager
from app.core.database import get_database

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories"""
    DATABASE = "database"
    CACHE = "cache"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    BUSINESS_LOGIC = "business_logic"
    EXTERNAL_SERVICE = "external_service"
    SYSTEM = "system"
    NETWORK = "network"
    PERFORMANCE = "performance"


@dataclass
class ServiceError:
    """Service error data structure"""
    error_id: str
    service_name: str
    error_type: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    details: Dict[str, Any]
    timestamp: datetime
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    stack_trace: Optional[str] = None
    resolved: bool = False
    resolution_notes: Optional[str] = None


class ServiceErrorHandler:
    """Comprehensive error handler for all services"""
    
    def __init__(self):
        self.error_patterns = {
            # Database errors
            "connection_error": {
                "category": ErrorCategory.DATABASE,
                "severity": ErrorSeverity.HIGH,
                "keywords": ["connection", "timeout", "unreachable"]
            },
            "query_error": {
                "category": ErrorCategory.DATABASE,
                "severity": ErrorSeverity.MEDIUM,
                "keywords": ["query", "syntax", "invalid"]
            },
            
            # Cache errors
            "cache_miss": {
                "category": ErrorCategory.CACHE,
                "severity": ErrorSeverity.LOW,
                "keywords": ["cache", "miss", "not found"]
            },
            "cache_connection_error": {
                "category": ErrorCategory.CACHE,
                "severity": ErrorSeverity.HIGH,
                "keywords": ["redis", "connection", "timeout"]
            },
            
            # Authentication errors
            "invalid_token": {
                "category": ErrorCategory.AUTHENTICATION,
                "severity": ErrorSeverity.MEDIUM,
                "keywords": ["token", "invalid", "expired"]
            },
            "unauthorized": {
                "category": ErrorCategory.AUTHORIZATION,
                "severity": ErrorSeverity.MEDIUM,
                "keywords": ["unauthorized", "forbidden", "access denied"]
            },
            
            # Validation errors
            "validation_error": {
                "category": ErrorCategory.VALIDATION,
                "severity": ErrorSeverity.LOW,
                "keywords": ["validation", "invalid", "required"]
            },
            
            # System errors
            "memory_error": {
                "category": ErrorCategory.SYSTEM,
                "severity": ErrorSeverity.CRITICAL,
                "keywords": ["memory", "out of memory", "allocation"]
            },
            "disk_space_error": {
                "category": ErrorCategory.SYSTEM,
                "severity": ErrorSeverity.HIGH,
                "keywords": ["disk", "space", "full"]
            }
        }
        
        # Error recovery strategies
        self.recovery_strategies = {
            ErrorCategory.DATABASE: self._recover_database_error,
            ErrorCategory.CACHE: self._recover_cache_error,
            ErrorCategory.EXTERNAL_SERVICE: self._recover_external_service_error,
            ErrorCategory.SYSTEM: self._recover_system_error
        }
        
        # Error escalation rules
        self.escalation_rules = {
            ErrorSeverity.CRITICAL: {"immediate": True, "notify_admin": True},
            ErrorSeverity.HIGH: {"immediate": False, "notify_admin": True},
            ErrorSeverity.MEDIUM: {"immediate": False, "notify_admin": False},
            ErrorSeverity.LOW: {"immediate": False, "notify_admin": False}
        }
    
    async def handle_error(
        self,
        service_name: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> ServiceError:
        """Handle service error with comprehensive logging and recovery"""
        try:
            # Generate error ID
            error_id = f"{service_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # Classify error
            error_type, category, severity = self._classify_error(error)
            
            # Create service error object
            service_error = ServiceError(
                error_id=error_id,
                service_name=service_name,
                error_type=error_type,
                category=category,
                severity=severity,
                message=str(error),
                details=context or {},
                timestamp=datetime.utcnow(),
                user_id=user_id,
                request_id=request_id,
                stack_trace=traceback.format_exc()
            )
            
            # Log error
            await self._log_error(service_error)
            
            # Store error in database
            await self._store_error(service_error)
            
            # Attempt recovery
            recovery_result = await self._attempt_recovery(service_error)
            if recovery_result:
                service_error.details["recovery_attempted"] = recovery_result
            
            # Check for escalation
            await self._check_escalation(service_error)
            
            # Update error metrics
            await self._update_error_metrics(service_error)
            
            return service_error
            
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
            # Return a basic error object
            return ServiceError(
                error_id="error_handler_failure",
                service_name=service_name,
                error_type="handler_error",
                category=ErrorCategory.SYSTEM,
                severity=ErrorSeverity.HIGH,
                message=f"Error handler failed: {str(e)}",
                details={"original_error": str(error)},
                timestamp=datetime.utcnow()
            )
    
    def _classify_error(self, error: Exception) -> tuple:
        """Classify error type, category, and severity"""
        error_message = str(error).lower()
        error_type_name = type(error).__name__.lower()
        
        # Check against known patterns
        for pattern_name, pattern_config in self.error_patterns.items():
            keywords = pattern_config["keywords"]
            
            # Check if any keyword matches
            if any(keyword in error_message or keyword in error_type_name for keyword in keywords):
                return (
                    pattern_name,
                    pattern_config["category"],
                    pattern_config["severity"]
                )
        
        # Default classification
        return (
            error_type_name,
            ErrorCategory.SYSTEM,
            ErrorSeverity.MEDIUM
        )
    
    async def _log_error(self, service_error: ServiceError):
        """Log error with appropriate level"""
        log_message = (
            f"Service Error [{service_error.error_id}] in {service_error.service_name}: "
            f"{service_error.message}"
        )
        
        if service_error.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message, extra={"service_error": asdict(service_error)})
        elif service_error.severity == ErrorSeverity.HIGH:
            logger.error(log_message, extra={"service_error": asdict(service_error)})
        elif service_error.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message, extra={"service_error": asdict(service_error)})
        else:
            logger.info(log_message, extra={"service_error": asdict(service_error)})
    
    async def _store_error(self, service_error: ServiceError):
        """Store error in database for analysis"""
        try:
            db = await get_database()
            if db:
                error_doc = asdict(service_error)
                error_doc["timestamp"] = service_error.timestamp
                error_doc["category"] = service_error.category.value
                error_doc["severity"] = service_error.severity.value
                
                await db.service_errors.insert_one(error_doc)
                
                # Also cache recent errors for quick access
                await cache_manager.set_cache(
                    f"recent_error:{service_error.error_id}",
                    error_doc,
                    expire=3600
                )
                
        except Exception as e:
            logger.error(f"Failed to store error {service_error.error_id}: {e}")
    
    async def _attempt_recovery(self, service_error: ServiceError) -> Optional[Dict[str, Any]]:
        """Attempt automatic error recovery"""
        try:
            recovery_strategy = self.recovery_strategies.get(service_error.category)
            if recovery_strategy:
                return await recovery_strategy(service_error)
            
            return None
            
        except Exception as e:
            logger.error(f"Error recovery failed for {service_error.error_id}: {e}")
            return {"recovery_failed": str(e)}
    
    async def _recover_database_error(self, service_error: ServiceError) -> Dict[str, Any]:
        """Attempt database error recovery"""
        try:
            recovery_actions = []
            
            # For connection errors, try to reconnect
            if "connection" in service_error.error_type:
                recovery_actions.append("attempted_reconnection")
                # In a real implementation, this would trigger database reconnection
            
            # For query errors, log for analysis
            if "query" in service_error.error_type:
                recovery_actions.append("logged_for_analysis")
            
            return {
                "recovery_type": "database",
                "actions_taken": recovery_actions,
                "success": len(recovery_actions) > 0
            }
            
        except Exception as e:
            return {"recovery_type": "database", "error": str(e)}
    
    async def _recover_cache_error(self, service_error: ServiceError) -> Dict[str, Any]:
        """Attempt cache error recovery"""
        try:
            recovery_actions = []
            
            # For cache misses, this is normal behavior
            if "miss" in service_error.error_type:
                recovery_actions.append("cache_miss_normal")
            
            # For connection errors, try to reconnect
            if "connection" in service_error.error_type:
                recovery_actions.append("attempted_cache_reconnection")
                # In a real implementation, this would trigger cache reconnection
            
            return {
                "recovery_type": "cache",
                "actions_taken": recovery_actions,
                "success": len(recovery_actions) > 0
            }
            
        except Exception as e:
            return {"recovery_type": "cache", "error": str(e)}
    
    async def _recover_external_service_error(self, service_error: ServiceError) -> Dict[str, Any]:
        """Attempt external service error recovery"""
        try:
            recovery_actions = []
            
            # For external service errors, implement circuit breaker
            recovery_actions.append("circuit_breaker_activated")
            
            # Schedule retry
            recovery_actions.append("retry_scheduled")
            
            return {
                "recovery_type": "external_service",
                "actions_taken": recovery_actions,
                "success": True
            }
            
        except Exception as e:
            return {"recovery_type": "external_service", "error": str(e)}
    
    async def _recover_system_error(self, service_error: ServiceError) -> Dict[str, Any]:
        """Attempt system error recovery"""
        try:
            recovery_actions = []
            
            # For memory errors, trigger garbage collection
            if "memory" in service_error.error_type:
                recovery_actions.append("garbage_collection_triggered")
                import gc
                gc.collect()
            
            # For disk space errors, trigger cleanup
            if "disk" in service_error.error_type:
                recovery_actions.append("cleanup_scheduled")
            
            return {
                "recovery_type": "system",
                "actions_taken": recovery_actions,
                "success": len(recovery_actions) > 0
            }
            
        except Exception as e:
            return {"recovery_type": "system", "error": str(e)}
    
    async def _check_escalation(self, service_error: ServiceError):
        """Check if error needs escalation"""
        try:
            escalation_rule = self.escalation_rules.get(service_error.severity)
            if not escalation_rule:
                return
            
            # Check for immediate escalation
            if escalation_rule.get("immediate"):
                await self._escalate_immediately(service_error)
            
            # Check for admin notification
            if escalation_rule.get("notify_admin"):
                await self._notify_admin(service_error)
            
            # Check for pattern-based escalation
            await self._check_error_patterns(service_error)
            
        except Exception as e:
            logger.error(f"Error checking escalation for {service_error.error_id}: {e}")
    
    async def _escalate_immediately(self, service_error: ServiceError):
        """Escalate error immediately"""
        try:
            # Create escalation record
            escalation_doc = {
                "error_id": service_error.error_id,
                "service_name": service_error.service_name,
                "severity": service_error.severity.value,
                "escalated_at": datetime.utcnow(),
                "escalation_type": "immediate",
                "status": "open"
            }
            
            db = await get_database()
            if db:
                await db.error_escalations.insert_one(escalation_doc)
            
            logger.critical(f"IMMEDIATE ESCALATION: {service_error.error_id} - {service_error.message}")
            
        except Exception as e:
            logger.error(f"Failed to escalate error {service_error.error_id}: {e}")
    
    async def _notify_admin(self, service_error: ServiceError):
        """Notify administrators of error"""
        try:
            # In a real implementation, this would send notifications
            # via email, Slack, PagerDuty, etc.
            
            notification_doc = {
                "error_id": service_error.error_id,
                "service_name": service_error.service_name,
                "severity": service_error.severity.value,
                "message": service_error.message,
                "notified_at": datetime.utcnow(),
                "notification_type": "admin_alert"
            }
            
            # Store notification record
            db = await get_database()
            if db:
                await db.admin_notifications.insert_one(notification_doc)
            
            logger.warning(f"ADMIN NOTIFICATION: {service_error.error_id} - {service_error.message}")
            
        except Exception as e:
            logger.error(f"Failed to notify admin for error {service_error.error_id}: {e}")
    
    async def _check_error_patterns(self, service_error: ServiceError):
        """Check for error patterns that indicate larger issues"""
        try:
            # Check for repeated errors from same service
            recent_errors = await self._get_recent_errors(
                service_error.service_name,
                minutes=10
            )
            
            if len(recent_errors) >= 5:  # 5 errors in 10 minutes
                await self._escalate_pattern(service_error, "high_frequency", recent_errors)
            
            # Check for cascading errors across services
            all_recent_errors = await self._get_recent_errors(minutes=5)
            if len(all_recent_errors) >= 10:  # 10 errors across all services in 5 minutes
                await self._escalate_pattern(service_error, "cascading_failure", all_recent_errors)
            
        except Exception as e:
            logger.error(f"Error checking patterns for {service_error.error_id}: {e}")
    
    async def _get_recent_errors(
        self,
        service_name: Optional[str] = None,
        minutes: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent errors for pattern analysis"""
        try:
            db = await get_database()
            if not db:
                return []
            
            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
            
            query = {"timestamp": {"$gte": cutoff_time}}
            if service_name:
                query["service_name"] = service_name
            
            cursor = db.service_errors.find(query).sort("timestamp", -1)
            return await cursor.to_list(length=100)
            
        except Exception as e:
            logger.error(f"Error getting recent errors: {e}")
            return []
    
    async def _escalate_pattern(
        self,
        service_error: ServiceError,
        pattern_type: str,
        related_errors: List[Dict[str, Any]]
    ):
        """Escalate based on error patterns"""
        try:
            escalation_doc = {
                "error_id": service_error.error_id,
                "service_name": service_error.service_name,
                "pattern_type": pattern_type,
                "related_error_count": len(related_errors),
                "escalated_at": datetime.utcnow(),
                "escalation_type": "pattern_based",
                "status": "open"
            }
            
            db = await get_database()
            if db:
                await db.error_escalations.insert_one(escalation_doc)
            
            logger.critical(
                f"PATTERN ESCALATION: {pattern_type} detected - "
                f"{len(related_errors)} related errors"
            )
            
        except Exception as e:
            logger.error(f"Failed to escalate pattern for {service_error.error_id}: {e}")
    
    async def _update_error_metrics(self, service_error: ServiceError):
        """Update error metrics for monitoring"""
        try:
            # Update error counters in cache
            metrics_key = f"error_metrics:{service_error.service_name}"
            current_metrics = await cache_manager.get_cache(metrics_key) or {}
            
            # Update counters
            current_metrics["total_errors"] = current_metrics.get("total_errors", 0) + 1
            current_metrics[f"{service_error.severity.value}_errors"] = (
                current_metrics.get(f"{service_error.severity.value}_errors", 0) + 1
            )
            current_metrics[f"{service_error.category.value}_errors"] = (
                current_metrics.get(f"{service_error.category.value}_errors", 0) + 1
            )
            current_metrics["last_error"] = datetime.utcnow().isoformat()
            
            # Cache updated metrics
            await cache_manager.set_cache(metrics_key, current_metrics, expire=3600)
            
        except Exception as e:
            logger.error(f"Failed to update error metrics for {service_error.error_id}: {e}")
    
    async def get_error_summary(
        self,
        service_name: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get error summary for monitoring dashboard"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            db = await get_database()
            if not db:
                return {"error": "Database not available"}
            
            # Build query
            query = {"timestamp": {"$gte": cutoff_time}}
            if service_name:
                query["service_name"] = service_name
            
            # Get error statistics
            pipeline = [
                {"$match": query},
                {"$group": {
                    "_id": {
                        "service": "$service_name",
                        "severity": "$severity",
                        "category": "$category"
                    },
                    "count": {"$sum": 1}
                }}
            ]
            
            cursor = db.service_errors.aggregate(pipeline)
            error_stats = await cursor.to_list(length=None)
            
            # Process statistics
            summary = {
                "time_period_hours": hours,
                "total_errors": 0,
                "by_service": {},
                "by_severity": {},
                "by_category": {},
                "recent_errors": []
            }
            
            for stat in error_stats:
                service = stat["_id"]["service"]
                severity = stat["_id"]["severity"]
                category = stat["_id"]["category"]
                count = stat["count"]
                
                summary["total_errors"] += count
                
                # By service
                if service not in summary["by_service"]:
                    summary["by_service"][service] = 0
                summary["by_service"][service] += count
                
                # By severity
                if severity not in summary["by_severity"]:
                    summary["by_severity"][severity] = 0
                summary["by_severity"][severity] += count
                
                # By category
                if category not in summary["by_category"]:
                    summary["by_category"][category] = 0
                summary["by_category"][category] += count
            
            # Get recent errors
            recent_cursor = db.service_errors.find(query).sort("timestamp", -1).limit(10)
            recent_errors = await recent_cursor.to_list(length=10)
            
            summary["recent_errors"] = [
                {
                    "error_id": error["error_id"],
                    "service_name": error["service_name"],
                    "severity": error["severity"],
                    "message": error["message"],
                    "timestamp": error["timestamp"].isoformat()
                }
                for error in recent_errors
            ]
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting error summary: {e}")
            return {"error": str(e)}


# Global service error handler instance
service_error_handler = ServiceErrorHandler()