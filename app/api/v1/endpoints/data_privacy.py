"""
Data Privacy and FERPA Compliance Endpoints
Handles data access requests, deletion, and audit trails
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging

from app.core.auth import cognito_auth
from app.core.database import get_database
from app.models.user import UserProfile, UserRole
from app.services.data_privacy_service import DataPrivacyService
from app.api.v1.endpoints.users import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()


class DataAccessRequest(BaseModel):
    request_type: str  # "access", "deletion", "correction"
    details: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class DataDeletionRequest(BaseModel):
    preserve_analytics: bool = True
    confirmation: str  # Must be "DELETE_MY_DATA"
    reason: Optional[str] = None


class AuditTrailQuery(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    action_filter: Optional[str] = None
    limit: int = 100


def get_client_info(request: Request) -> Dict[str, str]:
    """Extract client IP and user agent from request"""
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent")
    }


@router.post("/data-request", response_model=Dict[str, Any])
async def create_data_request(
    request_data: DataAccessRequest,
    request: Request,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Create a formal data access, deletion, or correction request
    
    Complies with FERPA requirements for educational record requests.
    """
    try:
        privacy_service = DataPrivacyService(db)
        client_info = get_client_info(request)
        
        # Validate request type
        valid_types = ["access", "deletion", "correction"]
        if request_data.request_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request type. Must be one of: {valid_types}"
            )
        
        # Create data request
        request_id = await privacy_service.create_data_request(
            user_id=current_user.user_id,
            request_type=request_data.request_type,
            requesting_user_id=current_user.user_id,
            details=request_data.details,
            ip_address=client_info["ip_address"]
        )
        
        # Determine response timeline based on FERPA requirements
        response_timeline = {
            "access": "45 days",
            "deletion": "30 days", 
            "correction": "45 days"
        }
        
        return {
            "request_id": request_id,
            "status": "pending",
            "request_type": request_data.request_type,
            "created_at": datetime.utcnow().isoformat(),
            "estimated_response_time": response_timeline.get(request_data.request_type, "45 days"),
            "ferpa_compliance": {
                "applicable": True,
                "response_deadline": (datetime.utcnow() + timedelta(days=45)).isoformat()
            },
            "message": f"Your {request_data.request_type} request has been submitted and will be processed according to FERPA requirements."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating data request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create data request"
        )


@router.get("/my-data", response_model=Dict[str, Any])
async def get_my_complete_data(
    request: Request,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get complete user data export (FERPA compliance)
    
    Returns all data associated with the user's educational records.
    """
    try:
        privacy_service = DataPrivacyService(db)
        client_info = get_client_info(request)
        
        # Get complete user data
        complete_data = await privacy_service.get_complete_user_data(
            user_id=current_user.user_id,
            requesting_user_id=current_user.user_id,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"]
        )
        
        return complete_data
        
    except Exception as e:
        logger.error(f"Error retrieving complete user data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user data"
        )


@router.delete("/my-data", response_model=Dict[str, Any])
async def delete_my_data(
    deletion_request: DataDeletionRequest,
    request: Request,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Delete user data with analytics preservation option
    
    Complies with FERPA and GDPR right to be forgotten while allowing
    anonymized analytics preservation for educational research.
    """
    try:
        # Validate confirmation
        if deletion_request.confirmation != "DELETE_MY_DATA":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid confirmation. Must provide exact confirmation string."
            )
        
        privacy_service = DataPrivacyService(db)
        client_info = get_client_info(request)
        
        # Perform data deletion
        deletion_summary = await privacy_service.delete_user_data_with_analytics_preservation(
            user_id=current_user.user_id,
            requesting_user_id=current_user.user_id,
            preserve_analytics=deletion_request.preserve_analytics,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"]
        )
        
        return {
            "message": "User data deletion completed successfully",
            "deletion_summary": deletion_summary,
            "ferpa_compliance": {
                "deletion_completed": True,
                "analytics_preserved": deletion_request.preserve_analytics,
                "audit_trail_maintained": True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user data"
        )


@router.get("/audit-trail", response_model=List[Dict[str, Any]])
async def get_my_audit_trail(
    query: AuditTrailQuery = Depends(),
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get user's audit trail for transparency and compliance
    
    Shows all access and modifications to user's educational records.
    """
    try:
        privacy_service = DataPrivacyService(db)
        
        # Get audit trail
        audit_records = await privacy_service.get_audit_trail(
            user_id=current_user.user_id,
            start_date=query.start_date,
            end_date=query.end_date,
            action_filter=query.action_filter,
            limit=query.limit
        )
        
        return audit_records
        
    except Exception as e:
        logger.error(f"Error retrieving audit trail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit trail"
        )


@router.get("/ferpa-compliance", response_model=Dict[str, Any])
async def check_ferpa_compliance(
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Check FERPA compliance status for user's data
    
    Provides transparency about data retention and compliance status.
    """
    try:
        privacy_service = DataPrivacyService(db)
        
        # Check compliance
        compliance_report = await privacy_service.check_ferpa_compliance(current_user.user_id)
        
        return compliance_report
        
    except Exception as e:
        logger.error(f"Error checking FERPA compliance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check FERPA compliance"
        )


# Admin endpoints for managing data requests

@router.get("/admin/data-requests", response_model=List[Dict[str, Any]])
async def list_data_requests(
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database),
    status_filter: Optional[str] = None,
    request_type: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """
    List data requests (Admin only)
    
    Allows administrators to manage and process data requests.
    """
    # Check admin permissions
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        privacy_service = DataPrivacyService(db)
        
        # Build query
        query = {}
        if status_filter:
            query["status"] = status_filter
        if request_type:
            query["request_type"] = request_type
        
        # Get data requests
        cursor = privacy_service.data_requests_collection.find(query).skip(skip).limit(limit)
        requests = await cursor.to_list(length=limit)
        
        # Remove MongoDB _id field
        for request_doc in requests:
            request_doc.pop("_id", None)
        
        return requests
        
    except Exception as e:
        logger.error(f"Error listing data requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list data requests"
        )


@router.put("/admin/data-requests/{request_id}/status")
async def update_data_request_status(
    request_id: str,
    status: str,
    processing_notes: Optional[str] = None,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Update data request status (Admin only)
    
    Allows administrators to process and update data request status.
    """
    # Check admin permissions
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        privacy_service = DataPrivacyService(db)
        
        # Validate status
        valid_statuses = ["pending", "in_progress", "completed", "rejected"]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {valid_statuses}"
            )
        
        # Update status
        success = await privacy_service.update_data_request_status(
            request_id=request_id,
            status=status,
            processing_notes=processing_notes,
            completed_by=current_user.user_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data request not found"
            )
        
        return {
            "message": "Data request status updated successfully",
            "request_id": request_id,
            "new_status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating data request status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update data request status"
        )


@router.get("/admin/users/{user_id}/data", response_model=Dict[str, Any])
async def get_user_data_admin(
    user_id: str,
    request: Request,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get complete user data (Admin only)
    
    Allows administrators to access user data for compliance purposes.
    """
    # Check admin permissions
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        privacy_service = DataPrivacyService(db)
        client_info = get_client_info(request)
        
        # Get complete user data
        complete_data = await privacy_service.get_complete_user_data(
            user_id=user_id,
            requesting_user_id=current_user.user_id,
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"]
        )
        
        return complete_data
        
    except Exception as e:
        logger.error(f"Error retrieving user data for admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user data"
        )


@router.get("/admin/audit-trail/{user_id}", response_model=List[Dict[str, Any]])
async def get_user_audit_trail_admin(
    user_id: str,
    query: AuditTrailQuery = Depends(),
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get user's audit trail (Admin only)
    
    Allows administrators to review audit trails for compliance purposes.
    """
    # Check admin permissions
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        privacy_service = DataPrivacyService(db)
        
        # Get audit trail
        audit_records = await privacy_service.get_audit_trail(
            user_id=user_id,
            start_date=query.start_date,
            end_date=query.end_date,
            action_filter=query.action_filter,
            limit=query.limit
        )
        
        return audit_records
        
    except Exception as e:
        logger.error(f"Error retrieving audit trail for admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit trail"
        )