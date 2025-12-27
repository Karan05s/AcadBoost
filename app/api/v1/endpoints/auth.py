"""
Authentication endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Dict, Any
from datetime import datetime
import logging

from app.core.auth import cognito_auth
from app.core.database import get_database
from app.models.user import UserRegistration, UserLogin, UserProfile, UserRole
from app.services.user_service import UserService
from app.services.security_service import SecurityService, SecurityEventType
from app.core.security_middleware import get_current_user, ensure_own_data_access

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    confirmation_code: str
    new_password: str


class EmailVerificationRequest(BaseModel):
    email: EmailStr
    confirmation_code: str


@router.post("/register", response_model=Dict[str, Any])
async def register(
    user_data: UserRegistration,
    background_tasks: BackgroundTasks,
    db=Depends(get_database)
):
    """
    User registration endpoint with email verification
    
    Creates a new user account in AWS Cognito and stores profile in MongoDB.
    Sends email verification automatically.
    """
    try:
        # Register user with AWS Cognito
        cognito_response = await cognito_auth.register_user(
            email=user_data.email,
            password=user_data.password,
            username=user_data.username
        )
        
        # Create user profile in MongoDB
        user_service = UserService(db)
        profile = await user_service.create_user_profile(
            user_id=cognito_response['user_id'],
            email=user_data.email,
            username=user_data.username,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=user_data.role,
            institution=user_data.institution
        )
        
        # Send email verification (background task)
        background_tasks.add_task(
            cognito_auth.send_email_verification,
            user_data.username
        )
        
        return {
            "message": "User registered successfully. Please check your email for verification.",
            "user_id": profile.user_id,
            "email": profile.email,
            "email_verified": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/login", response_model=Dict[str, Any])
async def login(
    credentials: UserLogin,
    request: Request,
    db=Depends(get_database)
):
    """
    Optimized user login endpoint with JWT token validation and cached dashboard data
    
    Authenticates user with AWS Cognito and returns pre-computed dashboard data.
    Performance optimized with single aggregated query and Redis caching.
    Includes security event logging and session management.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    security_service = SecurityService(db)
    
    try:
        # Authenticate with AWS Cognito
        auth_response = await cognito_auth.authenticate_user(
            username=credentials.username,
            password=credentials.password
        )
        
        # Verify JWT token for security
        token_data = await cognito_auth.verify_token(auth_response['access_token'])
        
        # Get user service instance
        user_service = UserService(db)
        
        # Get user profile from database
        profile = await user_service.get_user_by_cognito_id(token_data['user_id'])
        if not profile:
            await security_service.log_security_event(
                event_type=SecurityEventType.FAILED_LOGIN,
                user_id=token_data.get('user_id'),
                ip_address=client_ip,
                user_agent=user_agent,
                details={"reason": "profile_not_found", "username": credentials.username}
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        # Create user session
        await security_service.create_user_session(
            user_id=profile.user_id,
            session_token=auth_response['access_token'],
            ip_address=client_ip,
            user_agent=user_agent
        )
        
        # Update last login timestamp (async, non-blocking)
        await user_service.update_last_login(profile.user_id)
        
        # Get optimized dashboard data (single aggregated query with Redis caching)
        dashboard_data = await user_service.get_dashboard_data(profile.user_id)
        
        # Log successful login
        logger.info(f"Successful login for user {profile.user_id} from IP {client_ip}")
        
        # Return aggregated login response with all necessary data
        return {
            "access_token": auth_response['access_token'],
            "refresh_token": auth_response['refresh_token'],
            "token_type": "bearer",
            "expires_in": auth_response['expires_in'],
            "user": {
                "user_id": profile.user_id,
                "email": profile.email,
                "username": profile.username,
                "role": profile.role.value if hasattr(profile.role, 'value') else profile.role,
                "profile_completed": profile.profile_completed,
                "onboarding_completed": profile.onboarding_completed,
                "learning_preferences": profile.learning_preferences,
                "academic_info": profile.academic_info
            },
            "dashboard": dashboard_data,
            "login_timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException as e:
        # Log failed login attempt
        await security_service.log_security_event(
            event_type=SecurityEventType.FAILED_LOGIN,
            ip_address=client_ip,
            user_agent=user_agent,
            details={
                "username": credentials.username,
                "error": str(e.detail),
                "status_code": e.status_code
            }
        )
        raise
    except Exception as e:
        # Log failed login attempt
        await security_service.log_security_event(
            event_type=SecurityEventType.FAILED_LOGIN,
            ip_address=client_ip,
            user_agent=user_agent,
            details={
                "username": credentials.username,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    User logout endpoint with session invalidation and security logging
    
    Invalidates the current session, clears cached data, and logs the logout event.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    security_service = SecurityService(db)
    
    try:
        user_id = current_user["user_id"]
        
        # Get the current session token from the Authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header[7:]  # Remove "Bearer " prefix
            
            # Invalidate the session
            await security_service.invalidate_user_session(session_token)
        
        # Clear user session cache
        user_service = UserService(db)
        await user_service.clear_user_cache(user_id)
        
        # Log successful logout
        logger.info(f"User {user_id} logged out from IP {client_ip}")
        
        return {"message": "Logged out successfully"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.post("/refresh", response_model=Dict[str, Any])
async def refresh_token(refresh_token: str):
    """
    Token refresh endpoint
    
    Refreshes access token using refresh token.
    """
    try:
        auth_response = await cognito_auth.refresh_token(refresh_token)
        
        return {
            "access_token": auth_response['access_token'],
            "token_type": "bearer",
            "expires_in": auth_response['expires_in']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.post("/verify-email")
async def verify_email(
    verification_data: EmailVerificationRequest,
    db=Depends(get_database)
):
    """
    Email verification endpoint
    
    Confirms user email address using verification code.
    """
    try:
        # Verify email with Cognito
        await cognito_auth.confirm_email_verification(
            username=verification_data.email,
            confirmation_code=verification_data.confirmation_code
        )
        
        # Update user profile to mark email as verified
        user_service = UserService(db)
        await user_service.mark_email_verified(verification_data.email)
        
        return {"message": "Email verified successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email verification failed"
        )


@router.post("/reset-password")
async def reset_password(reset_request: PasswordResetRequest):
    """
    Password reset request endpoint
    
    Initiates password reset process by sending reset code to email.
    """
    try:
        await cognito_auth.initiate_password_reset(reset_request.email)
        
        return {"message": "Password reset code sent to your email"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset initiation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )


@router.post("/reset-password/confirm")
async def confirm_password_reset(reset_data: PasswordResetConfirm):
    """
    Password reset confirmation endpoint
    
    Confirms password reset using verification code and sets new password.
    """
    try:
        await cognito_auth.confirm_password_reset(
            username=reset_data.email,
            confirmation_code=reset_data.confirmation_code,
            new_password=reset_data.new_password
        )
        
        return {"message": "Password reset successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset confirmation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset confirmation failed"
        )


@router.get("/profile/data-export")
async def export_user_data(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Export user data for FERPA compliance
    
    Returns all stored data associated with the user account.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    security_service = SecurityService(db)
    
    try:
        user_id = current_user["user_id"]
        
        # Log data export request
        await security_service.log_security_event(
            event_type=SecurityEventType.DATA_EXPORT_REQUEST,
            user_id=user_id,
            ip_address=client_ip,
            user_agent=user_agent,
            details={"export_type": "full_user_data"}
        )
        
        # Collect all user data from various collections
        user_data = {
            "profile": current_user["profile"].__dict__ if hasattr(current_user["profile"], '__dict__') else current_user["profile"],
            "performance_data": [],
            "learning_gaps": [],
            "recommendations": [],
            "onboarding_data": None,
            "assessments": []
        }
        
        # Get performance data
        performance_cursor = db.student_performance.find({"student_id": user_id})
        user_data["performance_data"] = await performance_cursor.to_list(length=None)
        
        # Get learning gaps
        gaps_cursor = db.learning_gaps.find({"student_id": user_id})
        user_data["learning_gaps"] = await gaps_cursor.to_list(length=None)
        
        # Get recommendations
        recommendations_cursor = db.recommendations.find({"student_id": user_id})
        user_data["recommendations"] = await recommendations_cursor.to_list(length=None)
        
        # Get onboarding data
        user_data["onboarding_data"] = await db.user_onboarding.find_one({"user_id": user_id})
        
        # Get assessments
        assessments_cursor = db.user_assessments.find({"user_id": user_id})
        user_data["assessments"] = await assessments_cursor.to_list(length=None)
        
        # Convert ObjectIds to strings for JSON serialization
        def convert_objectids(obj):
            if isinstance(obj, dict):
                return {k: convert_objectids(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_objectids(item) for item in obj]
            elif hasattr(obj, '__dict__'):
                return convert_objectids(obj.__dict__)
            elif str(type(obj)) == "<class 'bson.objectid.ObjectId'>":
                return str(obj)
            else:
                return obj
        
        user_data = convert_objectids(user_data)
        
        return {
            "message": "User data export completed",
            "export_timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "data": user_data
        }
        
    except Exception as e:
        logger.error(f"Data export error for user {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Data export failed"
        )


@router.delete("/profile/data-deletion")
async def request_data_deletion(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Request user data deletion for FERPA compliance
    
    Deletes all personal data while preserving anonymized analytics.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    security_service = SecurityService(db)
    
    try:
        user_id = current_user["user_id"]
        
        # Log data deletion request
        await security_service.log_security_event(
            event_type=SecurityEventType.DATA_DELETION_REQUEST,
            user_id=user_id,
            ip_address=client_ip,
            user_agent=user_agent,
            details={"deletion_type": "full_user_data"}
        )
        
        # Delete user data from all collections
        deletion_results = {}
        
        # Delete user profile
        user_service = UserService(db)
        profile_deleted = await user_service.delete_user_profile(user_id)
        deletion_results["profile"] = profile_deleted
        
        # Delete performance data (anonymize instead of delete for analytics)
        performance_result = await db.student_performance.update_many(
            {"student_id": user_id},
            {"$set": {"student_id": "anonymized", "anonymized_at": datetime.utcnow()}}
        )
        deletion_results["performance_data"] = performance_result.modified_count
        
        # Delete learning gaps
        gaps_result = await db.learning_gaps.delete_many({"student_id": user_id})
        deletion_results["learning_gaps"] = gaps_result.deleted_count
        
        # Delete recommendations
        recommendations_result = await db.recommendations.delete_many({"student_id": user_id})
        deletion_results["recommendations"] = recommendations_result.deleted_count
        
        # Delete onboarding data
        onboarding_result = await db.user_onboarding.delete_many({"user_id": user_id})
        deletion_results["onboarding_data"] = onboarding_result.deleted_count
        
        # Delete assessments
        assessments_result = await db.user_assessments.delete_many({"user_id": user_id})
        deletion_results["assessments"] = assessments_result.deleted_count
        
        # Invalidate all user sessions
        sessions_result = await db.user_sessions.update_many(
            {"user_id": user_id},
            {"$set": {"active": False, "deleted_at": datetime.utcnow()}}
        )
        deletion_results["sessions"] = sessions_result.modified_count
        
        return {
            "message": "User data deletion completed",
            "deletion_timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "deletion_results": deletion_results
        }
        
    except Exception as e:
        logger.error(f"Data deletion error for user {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Data deletion failed"
        )