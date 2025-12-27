"""
Security management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.core.database import get_database
from app.services.security_service import SecurityService, SecurityEventType
from app.services.security_monitoring_service import SecurityMonitoringService
from app.core.security_middleware import get_current_user, RoleBasedAccessControl
from app.models.user import UserRole

router = APIRouter()


class SecurityEventQuery(BaseModel):
    """Query parameters for security events"""
    event_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 100


class DataIntegrityCheckRequest(BaseModel):
    """Request model for data integrity checks"""
    collection_name: str
    sample_size: int = 100


class UnauthorizedAccessCheckRequest(BaseModel):
    """Request model for unauthorized access detection"""
    user_id: str
    resource_id: str
    resource_type: str
    access_type: str
    user_role: str


@router.get("/events", response_model=List[Dict[str, Any]])
async def get_security_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    limit: int = Query(100, description="Maximum number of events to return"),
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Get security events (Admin only)
    
    Returns security events for monitoring and auditing purposes.
    """
    try:
        security_service = SecurityService(db)
        
        # Convert string event type to enum if provided
        event_type_enum = None
        if event_type:
            try:
                event_type_enum = SecurityEventType(event_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event type: {event_type}"
                )
        
        events = await security_service.get_security_events(
            event_type=event_type_enum,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return events
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve security events"
        )


@router.get("/events/user/{user_id}", response_model=List[Dict[str, Any]])
async def get_user_security_events(
    user_id: str,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    limit: int = Query(50, description="Maximum number of events to return"),
    current_user: dict = Depends(RoleBasedAccessControl.require_instructor_or_above()),
    db=Depends(get_database)
):
    """
    Get security events for a specific user (Instructor/Admin only)
    
    Returns security events related to a specific user.
    """
    try:
        security_service = SecurityService(db)
        
        # Convert string event type to enum if provided
        event_type_enum = None
        if event_type:
            try:
                event_type_enum = SecurityEventType(event_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event type: {event_type}"
                )
        
        events = await security_service.get_security_events(
            user_id=user_id,
            event_type=event_type_enum,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        return events
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user security events"
        )


@router.get("/sessions", response_model=List[Dict[str, Any]])
async def get_active_sessions(
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Get active user sessions (Admin only)
    
    Returns list of currently active user sessions.
    """
    try:
        # Get active sessions from database
        cursor = db.user_sessions.find({
            "active": True,
            "expires_at": {"$gt": datetime.utcnow()}
        }).sort("created_at", -1).limit(100)
        
        sessions = await cursor.to_list(length=100)
        
        # Remove sensitive session tokens from response
        for session in sessions:
            if "session_token" in session:
                session["session_token"] = "***REDACTED***"
        
        return sessions
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active sessions"
        )


@router.delete("/sessions/{session_id}")
async def invalidate_session(
    session_id: str,
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Invalidate a specific session (Admin only)
    
    Forcibly invalidates a user session.
    """
    try:
        security_service = SecurityService(db)
        
        # Find session by ID
        session = await db.user_sessions.find_one({"_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Invalidate the session
        success = await security_service.invalidate_user_session(session["session_token"])
        
        if success:
            # Log the admin action
            await security_service.log_security_event(
                event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
                user_id=current_user["user_id"],
                details={
                    "action": "admin_session_invalidation",
                    "target_session_id": session_id,
                    "target_user_id": session.get("user_id")
                }
            )
            
            return {"message": "Session invalidated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to invalidate session"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to invalidate session"
        )


@router.post("/cleanup/expired-sessions")
async def cleanup_expired_sessions(
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Clean up expired sessions (Admin only)
    
    Removes expired sessions from the database.
    """
    try:
        security_service = SecurityService(db)
        
        cleaned_count = await security_service.cleanup_expired_sessions()
        
        # Log the cleanup action
        await security_service.log_security_event(
            event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
            user_id=current_user["user_id"],
            details={
                "action": "admin_session_cleanup",
                "cleaned_sessions_count": cleaned_count
            }
        )
        
        return {
            "message": "Expired sessions cleaned up successfully",
            "cleaned_count": cleaned_count
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clean up expired sessions"
        )


@router.get("/permissions/check")
async def check_user_permissions(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Check current user's permissions
    
    Returns the permissions available to the current user based on their role.
    """
    try:
        security_service = SecurityService(db)
        user_role = current_user["role"]
        
        # Get permissions for user role
        permissions = security_service.role_permissions.get(user_role, [])
        
        return {
            "user_id": current_user["user_id"],
            "role": user_role.value if hasattr(user_role, 'value') else str(user_role),
            "permissions": [perm.value for perm in permissions]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check user permissions"
        )


@router.get("/dashboard/security-summary")
async def get_security_dashboard(
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Get security dashboard summary (Admin only)
    
    Returns security metrics and recent events for monitoring.
    """
    try:
        # Get recent security events (last 24 hours)
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        # Count events by type
        event_counts = {}
        for event_type in SecurityEventType:
            count = await db.security_events.count_documents({
                "event_type": event_type.value,
                "timestamp": {"$gte": cutoff_time}
            })
            event_counts[event_type.value] = count
        
        # Get active sessions count
        active_sessions = await db.user_sessions.count_documents({
            "active": True,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        # Get recent high-severity events
        recent_high_severity = await db.security_events.find({
            "severity": "HIGH",
            "timestamp": {"$gte": cutoff_time}
        }).sort("timestamp", -1).limit(10).to_list(length=10)
        
        return {
            "summary": {
                "active_sessions": active_sessions,
                "events_last_24h": sum(event_counts.values()),
                "high_severity_events_last_24h": event_counts.get("unauthorized_access", 0) + 
                                                event_counts.get("data_access_violation", 0) + 
                                                event_counts.get("suspicious_activity", 0)
            },
            "event_counts": event_counts,
            "recent_high_severity_events": recent_high_severity_events
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve security dashboard"
        )


@router.post("/monitoring/log-event")
async def log_security_event(
    request: Request,
    event_type: str,
    user_id: Optional[str] = None,
    resource_accessed: Optional[str] = None,
    event_details: Optional[Dict[str, Any]] = None,
    severity: str = "info",
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Log a security event (Admin only)
    
    Manually log security events for monitoring and analysis.
    """
    try:
        monitoring_service = SecurityMonitoringService(db)
        
        # Get client information
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent")
        
        event_id = await monitoring_service.log_security_event(
            event_type=event_type,
            user_id=user_id,
            ip_address=client_ip,
            user_agent=user_agent,
            resource_accessed=resource_accessed,
            event_details=event_details or {},
            severity=severity,
            source="manual"
        )
        
        return {
            "message": "Security event logged successfully",
            "event_id": event_id
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to log security event: {str(e)}"
        )


@router.post("/monitoring/check-unauthorized-access")
async def check_unauthorized_access(
    request: Request,
    check_request: UnauthorizedAccessCheckRequest,
    current_user: dict = Depends(RoleBasedAccessControl.require_instructor_or_above()),
    db=Depends(get_database)
):
    """
    Check for unauthorized access attempts (Instructor/Admin only)
    
    Analyze access patterns to detect unauthorized access attempts.
    """
    try:
        monitoring_service = SecurityMonitoringService(db)
        
        client_ip = request.client.host if request.client else "unknown"
        
        is_unauthorized = await monitoring_service.detect_unauthorized_access(
            user_id=check_request.user_id,
            resource_id=check_request.resource_id,
            resource_type=check_request.resource_type,
            access_type=check_request.access_type,
            user_role=check_request.user_role,
            ip_address=client_ip
        )
        
        return {
            "unauthorized_access_detected": is_unauthorized,
            "user_id": check_request.user_id,
            "resource_id": check_request.resource_id,
            "resource_type": check_request.resource_type,
            "access_type": check_request.access_type
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check unauthorized access: {str(e)}"
        )


@router.post("/monitoring/data-integrity-check")
async def perform_data_integrity_check(
    check_request: DataIntegrityCheckRequest,
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Perform data integrity check (Admin only)
    
    Check data integrity for a specific collection and detect corruption.
    """
    try:
        monitoring_service = SecurityMonitoringService(db)
        
        # Define expected schemas for different collections
        collection_schemas = {
            "users": {
                "user_id": {"type": "string", "required": True},
                "email": {"type": "string", "required": True, "validation": {"pattern": r"^[^@]+@[^@]+\.[^@]+$"}},
                "username": {"type": "string", "required": True, "validation": {"min_length": 3}},
                "created_at": {"type": "datetime", "required": True},
                "role": {"type": "string", "required": True}
            },
            "student_performance": {
                "student_id": {"type": "string", "required": True},
                "submission_type": {"type": "string", "required": True},
                "timestamp": {"type": "datetime", "required": True},
                "score": {"type": "float", "required": True}
            },
            "learning_gaps": {
                "student_id": {"type": "string", "required": True},
                "concept_id": {"type": "string", "required": True},
                "gap_severity": {"type": "float", "required": True},
                "confidence_score": {"type": "float", "required": True}
            }
        }
        
        expected_schema = collection_schemas.get(check_request.collection_name, {})
        
        if not expected_schema:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No schema defined for collection: {check_request.collection_name}"
            )
        
        # Get sample data from collection
        collection = db[check_request.collection_name]
        sample_data = await collection.find().limit(check_request.sample_size).to_list(length=check_request.sample_size)
        
        if not sample_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data found in collection: {check_request.collection_name}"
            )
        
        # Perform integrity check
        corruption_results = await monitoring_service.monitor_data_corruption(
            collection_name=check_request.collection_name,
            data_sample=sample_data,
            expected_schema=expected_schema
        )
        
        return corruption_results
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform data integrity check: {str(e)}"
        )


@router.get("/monitoring/dashboard")
async def get_security_monitoring_dashboard(
    start_date: Optional[datetime] = Query(None, description="Start date for analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for analysis"),
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Get comprehensive security monitoring dashboard (Admin only)
    
    Returns detailed security monitoring data including events, alerts, and compliance violations.
    """
    try:
        monitoring_service = SecurityMonitoringService(db)
        
        dashboard_data = await monitoring_service.get_security_dashboard_data(
            start_date=start_date,
            end_date=end_date
        )
        
        return dashboard_data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve security monitoring dashboard: {str(e)}"
        )


@router.get("/monitoring/alerts")
async def get_security_alerts(
    severity: Optional[str] = Query(None, description="Filter by alert severity"),
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    limit: int = Query(50, description="Maximum number of alerts to return"),
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Get security alerts (Admin only)
    
    Returns security alerts for monitoring and response.
    """
    try:
        query = {}
        
        if severity:
            query["severity"] = severity
        
        if resolved is not None:
            query["resolved"] = resolved
        
        cursor = db.security_alerts.find(query).sort("timestamp", -1).limit(limit)
        alerts = await cursor.to_list(length=limit)
        
        return alerts
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve security alerts: {str(e)}"
        )


@router.put("/monitoring/alerts/{alert_id}/acknowledge")
async def acknowledge_security_alert(
    alert_id: str,
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Acknowledge a security alert (Admin only)
    
    Mark a security alert as acknowledged.
    """
    try:
        result = await db.security_alerts.update_one(
            {"alert_id": alert_id},
            {
                "$set": {
                    "acknowledged": True,
                    "acknowledged_by": current_user["user_id"],
                    "acknowledged_at": datetime.utcnow()
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Security alert not found"
            )
        
        return {"message": "Security alert acknowledged successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to acknowledge security alert: {str(e)}"
        )


@router.get("/monitoring/compliance-violations")
async def get_compliance_violations(
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    regulation: Optional[str] = Query(None, description="Filter by regulation (e.g., FERPA)"),
    limit: int = Query(50, description="Maximum number of violations to return"),
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Get compliance violations (Admin only)
    
    Returns compliance violations for monitoring and remediation.
    """
    try:
        query = {}
        
        if resolved is not None:
            query["resolved"] = resolved
        
        if regulation:
            query["regulation"] = regulation
        
        cursor = db.compliance_violations.find(query).sort("timestamp", -1).limit(limit)
        violations = await cursor.to_list(length=limit)
        
        return violations
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve compliance violations: {str(e)}"
        )


@router.post("/monitoring/cleanup-old-events")
async def cleanup_old_security_events(
    retention_days: int = Query(90, description="Number of days to retain events"),
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Clean up old security events (Admin only)
    
    Remove old security events based on retention policy.
    """
    try:
        monitoring_service = SecurityMonitoringService(db)
        
        cleaned_count = await monitoring_service.cleanup_old_events(retention_days)
        
        # Log the cleanup action
        security_service = SecurityService(db)
        await security_service.log_security_event(
            event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
            user_id=current_user["user_id"],
            details={
                "action": "admin_security_events_cleanup",
                "retention_days": retention_days,
                "cleaned_events_count": cleaned_count
            }
        )
        
        return {
            "message": "Old security events cleaned up successfully",
            "cleaned_count": cleaned_count,
            "retention_days": retention_days
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clean up old security events: {str(e)}"
        )


@router.post("/monitoring/manual-scan")
async def run_manual_security_scan(
    current_user: dict = Depends(RoleBasedAccessControl.require_admin()),
    db=Depends(get_database)
):
    """
    Run manual comprehensive security scan (Admin only)
    
    Performs a comprehensive security scan including data integrity, threat analysis, and compliance checks.
    """
    try:
        from app.services.security_background_tasks import security_background_tasks
        
        # Initialize if not already done
        if not security_background_tasks.db:
            await security_background_tasks.initialize()
        
        # Run manual scan
        scan_results = await security_background_tasks.run_manual_security_scan()
        
        # Log the manual scan action
        security_service = SecurityService(db)
        await security_service.log_security_event(
            event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
            user_id=current_user["user_id"],
            details={
                "action": "manual_security_scan",
                "scan_id": scan_results.get("scan_id"),
                "initiated_by": current_user["user_id"]
            }
        )
        
        return scan_results
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run manual security scan: {str(e)}"
        )