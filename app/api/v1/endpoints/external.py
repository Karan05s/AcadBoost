"""
External API endpoints for third-party integrations and LMS systems
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
import hashlib
import hmac
import base64
import json
from urllib.parse import parse_qs, unquote

from app.core.database import get_database
from app.core.security_middleware import RateLimiter, APIKeyAuth
from app.core.versioning import get_api_version, create_versioned_response
from app.core.error_handling import create_error_response, get_request_id
from app.services.user_service import UserService
from app.services.data_collection_service import DataCollectionService
from app.services.analytics_service import AnalyticsService
from app.services.recommendation_service import RecommendationService
from app.models.performance import QuizSubmissionRequest, CodeSubmissionRequest
from app.models.user import UserProfile

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

# Rate limiter for external API endpoints
rate_limiter = RateLimiter(
    requests_per_minute=60,  # More restrictive for external APIs
    burst_limit=10
)

# API Key authentication for third-party services
api_key_auth = APIKeyAuth()


class LTILaunchRequest(BaseModel):
    """LTI 1.3 launch request model"""
    iss: str = Field(..., description="Issuer identifier")
    aud: str = Field(..., description="Audience")
    sub: str = Field(..., description="Subject identifier")
    exp: int = Field(..., description="Expiration time")
    iat: int = Field(..., description="Issued at time")
    nonce: str = Field(..., description="Nonce value")
    
    # LTI specific claims
    lti_version: str = Field("1.3.0", alias="https://purl.imsglobal.org/spec/lti/claim/version")
    message_type: str = Field(..., alias="https://purl.imsglobal.org/spec/lti/claim/message_type")
    deployment_id: str = Field(..., alias="https://purl.imsglobal.org/spec/lti/claim/deployment_id")
    target_link_uri: str = Field(..., alias="https://purl.imsglobal.org/spec/lti/claim/target_link_uri")
    
    # Context and resource claims
    context: Optional[Dict[str, Any]] = Field(None, alias="https://purl.imsglobal.org/spec/lti/claim/context")
    resource_link: Optional[Dict[str, Any]] = Field(None, alias="https://purl.imsglobal.org/spec/lti/claim/resource_link")
    
    # User information
    name: Optional[str] = None
    email: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    
    # Roles
    roles: List[str] = Field(default_factory=list, alias="https://purl.imsglobal.org/spec/lti/claim/roles")


class ExternalAPIResponse(BaseModel):
    """Standard response model for external API endpoints"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    api_version: str = "1.0"


class StudentAnalyticsRequest(BaseModel):
    """Request model for student analytics data"""
    student_ids: List[str] = Field(..., description="List of student identifiers")
    course_id: Optional[str] = Field(None, description="Course identifier")
    date_from: Optional[datetime] = Field(None, description="Start date for analytics")
    date_to: Optional[datetime] = Field(None, description="End date for analytics")
    include_recommendations: bool = Field(True, description="Include personalized recommendations")
    include_gaps: bool = Field(True, description="Include learning gap analysis")


class BulkSubmissionRequest(BaseModel):
    """Request model for bulk data submissions"""
    submissions: List[Dict[str, Any]] = Field(..., description="List of submissions")
    course_id: str = Field(..., description="Course identifier")
    assignment_id: Optional[str] = Field(None, description="Assignment identifier")
    validate_integrity: bool = Field(True, description="Validate data integrity")


@router.post("/lti/launch")
async def lti_launch(
    request: Request,
    lti_request: LTILaunchRequest,
    db=Depends(get_database)
):
    """
    LTI 1.3 launch endpoint for Learning Management System integration
    
    Handles LTI launch requests from external LMS platforms and creates/authenticates users.
    Requirements: 7.2 - Support standard protocols like LTI
    """
    client_ip = request.client.host if request.client else "unknown"
    request_id = get_request_id(request)
    api_version = get_api_version(request)
    
    try:
        # Apply rate limiting
        await rate_limiter.check_rate_limit(client_ip, "lti_launch")
        
        # Validate LTI request
        if not _validate_lti_request(lti_request):
            return create_error_response(
                error_key="VALIDATION_FIELD_INVALID",
                custom_message="Invalid LTI launch request",
                request_id=request_id,
                api_version=str(api_version)
            )
        
        # Extract user information
        user_service = UserService(db)
        
        # Check if user exists or create new user
        user_profile = await user_service.get_user_by_email(lti_request.email)
        
        if not user_profile:
            # Create new user from LTI data
            user_profile = await user_service.create_lti_user(
                email=lti_request.email,
                name=lti_request.name,
                given_name=lti_request.given_name,
                family_name=lti_request.family_name,
                roles=lti_request.roles,
                lti_context=lti_request.context,
                deployment_id=lti_request.deployment_id
            )
        
        # Generate session token for LTI user
        session_token = await user_service.create_lti_session(
            user_id=user_profile.user_id,
            lti_context=lti_request.context,
            resource_link=lti_request.resource_link,
            deployment_id=lti_request.deployment_id
        )
        
        # Get dashboard data for the user
        dashboard_data = await user_service.get_dashboard_data(user_profile.user_id)
        
        logger.info(f"LTI launch successful for user {user_profile.user_id} from {lti_request.iss}")
        
        return create_versioned_response(
            success=True,
            message="LTI launch successful",
            data={
                "session_token": session_token,
                "user": {
                    "user_id": user_profile.user_id,
                    "email": user_profile.email,
                    "name": f"{user_profile.first_name} {user_profile.last_name}",
                    "role": user_profile.role
                },
                "dashboard": dashboard_data,
                "lti_context": lti_request.context,
                "resource_link": lti_request.resource_link
            },
            version=api_version
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LTI launch error: {e}")
        return create_error_response(
            error_key="EXTERNAL_SERVICE_UNAVAILABLE",
            custom_message="LTI launch failed",
            request_id=request_id,
            api_version=str(api_version)
        )


@router.get("/analytics/students")
async def get_student_analytics(
    request: Request,
    student_ids: str,
    course_id: Optional[str] = None,
    include_recommendations: bool = True,
    include_gaps: bool = True,
    api_key: str = Depends(api_key_auth),
    db=Depends(get_database)
):
    """
    Get analytics data for multiple students (third-party API)
    
    Requirements: 7.3 - Provide secure API endpoints with proper authentication
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # Apply rate limiting
        await rate_limiter.check_rate_limit(client_ip, f"analytics_{api_key}")
        
        # Parse student IDs
        student_id_list = [sid.strip() for sid in student_ids.split(",")]
        
        if len(student_id_list) > 100:  # Limit bulk requests
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 100 students per request"
            )
        
        analytics_service = AnalyticsService(db)
        recommendation_service = RecommendationService(db)
        
        analytics_data = {}
        
        for student_id in student_id_list:
            student_analytics = {
                "student_id": student_id,
                "performance_summary": await analytics_service.get_performance_summary(student_id, course_id),
                "progress_trends": await analytics_service.get_progress_trends(student_id, course_id)
            }
            
            if include_gaps:
                student_analytics["learning_gaps"] = await analytics_service.get_learning_gaps(student_id)
            
            if include_recommendations:
                student_analytics["recommendations"] = await recommendation_service.get_recommendations(student_id)
            
            analytics_data[student_id] = student_analytics
        
        logger.info(f"Analytics data provided for {len(student_id_list)} students via API key {api_key[:8]}...")
        
        return ExternalAPIResponse(
            success=True,
            message=f"Analytics data retrieved for {len(student_id_list)} students",
            data={
                "students": analytics_data,
                "course_id": course_id,
                "generated_at": datetime.utcnow().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Student analytics API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve student analytics"
        )


@router.post("/submissions/bulk", response_model=ExternalAPIResponse)
async def bulk_submit_data(
    request: Request,
    bulk_request: BulkSubmissionRequest,
    api_key: str = Depends(api_key_auth),
    db=Depends(get_database)
):
    """
    Bulk submission endpoint for external systems
    
    Requirements: 7.1 - Provide RESTful APIs with comprehensive documentation
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # Apply rate limiting
        await rate_limiter.check_rate_limit(client_ip, f"bulk_submit_{api_key}")
        
        if len(bulk_request.submissions) > 1000:  # Limit bulk submissions
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 1000 submissions per bulk request"
            )
        
        data_service = DataCollectionService(db)
        
        results = {
            "successful": 0,
            "failed": 0,
            "errors": []
        }
        
        for i, submission_data in enumerate(bulk_request.submissions):
            try:
                # Add course and assignment context
                submission_data["course_id"] = bulk_request.course_id
                if bulk_request.assignment_id:
                    submission_data["assignment_id"] = bulk_request.assignment_id
                
                # Validate data integrity if requested
                if bulk_request.validate_integrity:
                    integrity_report = await data_service.validate_data_integrity(submission_data)
                    if not integrity_report["valid"]:
                        results["errors"].append({
                            "index": i,
                            "error": "Data integrity validation failed",
                            "details": integrity_report["errors"]
                        })
                        results["failed"] += 1
                        continue
                
                # Process submission based on type
                submission_type = submission_data.get("submission_type", "quiz")
                
                if submission_type == "quiz":
                    quiz_submission = QuizSubmissionRequest(**submission_data)
                    await data_service.process_quiz_submission(quiz_submission)
                elif submission_type == "code":
                    code_submission = CodeSubmissionRequest(**submission_data)
                    await data_service.process_code_submission(code_submission)
                else:
                    results["errors"].append({
                        "index": i,
                        "error": f"Unknown submission type: {submission_type}"
                    })
                    results["failed"] += 1
                    continue
                
                results["successful"] += 1
                
            except Exception as e:
                results["errors"].append({
                    "index": i,
                    "error": str(e)
                })
                results["failed"] += 1
        
        logger.info(f"Bulk submission processed: {results['successful']} successful, {results['failed']} failed")
        
        return ExternalAPIResponse(
            success=results["failed"] == 0,
            message=f"Bulk submission processed: {results['successful']} successful, {results['failed']} failed",
            data=results
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk submission error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk submission failed"
        )


@router.get("/health", response_model=ExternalAPIResponse)
async def external_api_health():
    """
    Health check endpoint for external API monitoring
    
    Requirements: 7.1 - RESTful API with comprehensive documentation
    """
    return ExternalAPIResponse(
        success=True,
        message="External API is healthy",
        data={
            "status": "operational",
            "endpoints": [
                "/lti/launch",
                "/analytics/students",
                "/submissions/bulk",
                "/webhooks/lms"
            ]
        }
    )


@router.post("/webhooks/lms", response_model=ExternalAPIResponse)
async def lms_webhook(
    request: Request,
    webhook_data: Dict[str, Any],
    x_signature: Optional[str] = Header(None),
    api_key: str = Depends(api_key_auth),
    db=Depends(get_database)
):
    """
    Webhook endpoint for LMS event notifications
    
    Requirements: 7.2 - LTI protocol support and LMS integration
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # Apply rate limiting
        await rate_limiter.check_rate_limit(client_ip, f"webhook_{api_key}")
        
        # Verify webhook signature if provided
        if x_signature:
            if not _verify_webhook_signature(webhook_data, x_signature, api_key):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
        
        # Process webhook event
        event_type = webhook_data.get("event_type")
        event_data = webhook_data.get("data", {})
        
        if event_type == "grade_updated":
            await _handle_grade_update(event_data, db)
        elif event_type == "assignment_submitted":
            await _handle_assignment_submission(event_data, db)
        elif event_type == "course_enrollment":
            await _handle_course_enrollment(event_data, db)
        elif event_type == "user_updated":
            await _handle_user_update(event_data, db)
        else:
            logger.warning(f"Unknown webhook event type: {event_type}")
        
        logger.info(f"Webhook processed: {event_type} from API key {api_key[:8]}...")
        
        return ExternalAPIResponse(
            success=True,
            message=f"Webhook event '{event_type}' processed successfully",
            data={"event_type": event_type}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failed"
        )


# Helper functions

def _validate_lti_request(lti_request: LTILaunchRequest) -> bool:
    """Validate LTI launch request"""
    try:
        # Check required fields
        if not all([lti_request.iss, lti_request.aud, lti_request.sub]):
            return False
        
        # Check expiration
        current_time = datetime.utcnow().timestamp()
        if lti_request.exp < current_time:
            return False
        
        # Check issued at time (not too old)
        if current_time - lti_request.iat > 300:  # 5 minutes
            return False
        
        # Validate LTI version
        if lti_request.lti_version != "1.3.0":
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"LTI validation error: {e}")
        return False


def _verify_webhook_signature(data: Dict[str, Any], signature: str, api_key: str) -> bool:
    """Verify webhook signature using HMAC"""
    try:
        # Create expected signature
        payload = json.dumps(data, sort_keys=True)
        expected_signature = hmac.new(
            api_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(signature, f"sha256={expected_signature}")
        
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


async def _handle_grade_update(event_data: Dict[str, Any], db):
    """Handle grade update webhook event"""
    try:
        student_id = event_data.get("student_id")
        assignment_id = event_data.get("assignment_id")
        grade = event_data.get("grade")
        max_grade = event_data.get("max_grade", 100)
        
        if not all([student_id, assignment_id, grade is not None]):
            logger.warning("Incomplete grade update data")
            return
        
        # Update performance data
        data_service = DataCollectionService(db)
        await data_service.update_grade_from_lms(
            student_id=student_id,
            assignment_id=assignment_id,
            score=float(grade),
            max_score=float(max_grade)
        )
        
        logger.info(f"Grade updated for student {student_id}, assignment {assignment_id}")
        
    except Exception as e:
        logger.error(f"Grade update handling error: {e}")


async def _handle_assignment_submission(event_data: Dict[str, Any], db):
    """Handle assignment submission webhook event"""
    try:
        student_id = event_data.get("student_id")
        assignment_id = event_data.get("assignment_id")
        submission_data = event_data.get("submission_data", {})
        
        if not all([student_id, assignment_id]):
            logger.warning("Incomplete assignment submission data")
            return
        
        # Process submission
        data_service = DataCollectionService(db)
        await data_service.process_lms_submission(
            student_id=student_id,
            assignment_id=assignment_id,
            submission_data=submission_data
        )
        
        logger.info(f"Assignment submission processed for student {student_id}")
        
    except Exception as e:
        logger.error(f"Assignment submission handling error: {e}")


async def _handle_course_enrollment(event_data: Dict[str, Any], db):
    """Handle course enrollment webhook event"""
    try:
        student_id = event_data.get("student_id")
        course_id = event_data.get("course_id")
        enrollment_status = event_data.get("status", "enrolled")
        
        if not all([student_id, course_id]):
            logger.warning("Incomplete course enrollment data")
            return
        
        # Update user enrollment
        user_service = UserService(db)
        await user_service.update_course_enrollment(
            user_id=student_id,
            course_id=course_id,
            status=enrollment_status
        )
        
        logger.info(f"Course enrollment updated for student {student_id}")
        
    except Exception as e:
        logger.error(f"Course enrollment handling error: {e}")


async def _handle_user_update(event_data: Dict[str, Any], db):
    """Handle user update webhook event"""
    try:
        user_id = event_data.get("user_id")
        updates = event_data.get("updates", {})
        
        if not user_id:
            logger.warning("Missing user_id in user update event")
            return
        
        # Update user profile
        user_service = UserService(db)
        await user_service.update_user_from_lms(user_id, updates)
        
        logger.info(f"User profile updated for user {user_id}")
        
    except Exception as e:
        logger.error(f"User update handling error: {e}")