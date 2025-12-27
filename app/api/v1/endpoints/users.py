"""
User management endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from app.core.auth import cognito_auth
from app.core.database import get_database
from app.models.user import UserProfile, UserProfileUpdate, UserRole, LearningStyle
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()


class LearningPreferences(BaseModel):
    learning_style: Optional[LearningStyle] = None
    study_time_preference: Optional[str] = None  # "morning" | "afternoon" | "evening" | "flexible"
    difficulty_preference: Optional[str] = None  # "gradual" | "challenging" | "adaptive"
    resource_preferences: Optional[List[str]] = None  # ["video", "text", "interactive", "practice"]
    notification_preferences: Optional[Dict[str, Any]] = None


class AcademicInfo(BaseModel):
    major: Optional[str] = None
    year: Optional[str] = None  # "freshman" | "sophomore" | "junior" | "senior" | "graduate"
    gpa: Optional[float] = None
    enrolled_courses: Optional[List[str]] = None


class OnboardingStep(BaseModel):
    step: str
    completed: bool = False
    data: Optional[Dict[str, Any]] = None


class OnboardingProgress(BaseModel):
    current_step: str
    completed_steps: List[str]
    total_steps: int
    progress_percentage: float


class InitialAssessment(BaseModel):
    questions: List[Dict[str, Any]]
    answers: List[Dict[str, Any]]
    skill_level: Optional[str] = None  # "beginner" | "intermediate" | "advanced"


class DashboardPersonalization(BaseModel):
    preferred_widgets: List[str]
    layout_preference: str  # "compact" | "detailed" | "minimal"
    theme_preference: str  # "light" | "dark" | "auto"


class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    institution: Optional[str] = None
    learning_preferences: Optional[LearningPreferences] = None
    academic_info: Optional[AcademicInfo] = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db=Depends(get_database)
) -> UserProfile:
    """Get current authenticated user"""
    try:
        # Verify token
        token_data = await cognito_auth.verify_token(credentials.credentials)
        
        # Get user profile
        user_service = UserService(db)
        profile = await user_service.get_user_by_cognito_id(token_data['user_id'])
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        return profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication"
        )


@router.get("/profile", response_model=UserProfile)
async def get_profile(current_user: UserProfile = Depends(get_current_user)):
    """
    Get user profile
    
    Returns complete user profile including learning preferences and academic info.
    """
    return current_user


@router.put("/profile", response_model=UserProfile)
async def update_profile(
    profile_update: ProfileUpdateRequest,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Update user profile
    
    Updates user profile information including learning preferences and academic info.
    """
    try:
        user_service = UserService(db)
        
        # Prepare update data
        update_data = {}
        
        if profile_update.first_name is not None:
            update_data["first_name"] = profile_update.first_name
        
        if profile_update.last_name is not None:
            update_data["last_name"] = profile_update.last_name
        
        if profile_update.institution is not None:
            update_data["institution"] = profile_update.institution
        
        if profile_update.learning_preferences is not None:
            update_data["learning_preferences"] = profile_update.learning_preferences.dict(exclude_none=True)
        
        if profile_update.academic_info is not None:
            update_data["academic_info"] = profile_update.academic_info.dict(exclude_none=True)
        
        # Check if profile is now complete
        if not current_user.profile_completed:
            required_fields = ["first_name", "last_name", "learning_preferences"]
            if all(field in update_data or getattr(current_user, field) for field in required_fields):
                update_data["profile_completed"] = True
        
        # Update profile
        success = await user_service.update_profile(current_user.user_id, update_data)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update profile"
            )
        
        # Get updated profile
        updated_profile = await user_service.get_user_by_cognito_id(current_user.user_id)
        
        # Clear cache
        await user_service.clear_user_cache(current_user.user_id)
        
        return updated_profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update failed"
        )


@router.delete("/profile")
async def delete_profile(
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Delete user profile
    
    Deletes user profile and all associated data (GDPR compliance).
    """
    try:
        user_service = UserService(db)
        
        # Delete user profile from database
        success = await user_service.delete_user_profile(current_user.user_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to delete profile"
            )
        
        return {"message": "Profile deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile deletion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile deletion failed"
        )


@router.get("/preferences", response_model=Dict[str, Any])
async def get_preferences(current_user: UserProfile = Depends(get_current_user)):
    """
    Get user learning preferences
    
    Returns detailed learning preferences for personalization.
    """
    return {
        "learning_preferences": current_user.learning_preferences or {},
        "academic_info": current_user.academic_info or {}
    }


@router.put("/preferences")
async def update_preferences(
    preferences: LearningPreferences,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Update user learning preferences
    
    Updates learning preferences for recommendation personalization.
    """
    try:
        user_service = UserService(db)
        
        # Update learning preferences
        update_data = {
            "learning_preferences": preferences.dict(exclude_none=True)
        }
        
        success = await user_service.update_profile(current_user.user_id, update_data)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update preferences"
            )
        
        # Clear cache
        await user_service.clear_user_cache(current_user.user_id)
        
        return {"message": "Preferences updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preferences update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Preferences update failed"
        )


@router.get("/academic-info", response_model=Dict[str, Any])
async def get_academic_info(current_user: UserProfile = Depends(get_current_user)):
    """
    Get user academic information
    
    Returns academic information for course recommendations.
    """
    return current_user.academic_info or {}


@router.put("/academic-info")
async def update_academic_info(
    academic_info: AcademicInfo,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Update user academic information
    
    Updates academic information for better course and content recommendations.
    """
    try:
        user_service = UserService(db)
        
        # Update academic info
        update_data = {
            "academic_info": academic_info.dict(exclude_none=True)
        }
        
        success = await user_service.update_profile(current_user.user_id, update_data)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update academic information"
            )
        
        # Clear cache
        await user_service.clear_user_cache(current_user.user_id)
        
        return {"message": "Academic information updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Academic info update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Academic information update failed"
        )


# Role-based access control endpoints
@router.get("/users", response_model=List[Dict[str, Any]])
async def list_users(
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database),
    role: Optional[str] = None,
    institution: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """
    List users (Admin/Instructor only)
    
    Returns list of users with role-based filtering.
    """
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.INSTRUCTOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    try:
        user_service = UserService(db)
        
        # Build query filters
        filters = {}
        if role:
            filters["role"] = role
        if institution:
            filters["institution"] = institution
        
        # For instructors, limit to their institution
        if current_user.role == UserRole.INSTRUCTOR:
            filters["institution"] = current_user.institution
        
        # Query users
        cursor = user_service.collection.find(filters).skip(skip).limit(limit)
        users = await cursor.to_list(length=limit)
        
        # Remove sensitive information
        safe_users = []
        for user in users:
            safe_user = {
                "user_id": user["user_id"],
                "email": user["email"],
                "username": user["username"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "role": user["role"],
                "institution": user["institution"],
                "created_at": user["created_at"],
                "last_login": user.get("last_login"),
                "profile_completed": user["profile_completed"],
                "onboarding_completed": user["onboarding_completed"]
            }
            safe_users.append(safe_user)
        
        return safe_users
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )


@router.get("/users/{user_id}", response_model=Dict[str, Any])
async def get_user_by_id(
    user_id: str,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get user by ID (Admin/Instructor only)
    
    Returns user profile with role-based access control.
    """
    # Check permissions
    if current_user.role not in [UserRole.ADMIN, UserRole.INSTRUCTOR]:
        # Users can only access their own profile
        if current_user.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
    
    try:
        user_service = UserService(db)
        user_profile = await user_service.get_user_by_cognito_id(user_id)
        
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # For instructors, ensure same institution
        if (current_user.role == UserRole.INSTRUCTOR and 
            user_profile.institution != current_user.institution):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return user_profile.dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user"
        )


# Onboarding Flow Endpoints

@router.post("/onboarding/start", response_model=Dict[str, Any])
async def start_onboarding(
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Start user onboarding process
    
    Initializes the guided onboarding flow and returns the first step.
    """
    try:
        user_service = UserService(db)
        
        # Initialize onboarding progress
        onboarding_data = await user_service.initialize_onboarding(current_user.user_id)
        
        return {
            "message": "Onboarding started successfully",
            "current_step": onboarding_data["current_step"],
            "progress": onboarding_data["progress"],
            "next_action": onboarding_data["next_action"]
        }
        
    except Exception as e:
        logger.error(f"Onboarding start error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start onboarding"
        )


@router.get("/onboarding/progress", response_model=OnboardingProgress)
async def get_onboarding_progress(
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get current onboarding progress
    
    Returns the user's current position in the onboarding flow.
    """
    try:
        user_service = UserService(db)
        progress = await user_service.get_onboarding_progress(current_user.user_id)
        
        return OnboardingProgress(**progress)
        
    except Exception as e:
        logger.error(f"Get onboarding progress error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get onboarding progress"
        )


@router.put("/onboarding/preferences")
async def update_onboarding_preferences(
    preferences: LearningPreferences,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Update learning preferences during onboarding
    
    Updates user learning preferences and advances onboarding progress.
    """
    try:
        user_service = UserService(db)
        
        # Update preferences and mark step as completed
        success = await user_service.complete_onboarding_step(
            current_user.user_id,
            "preferences",
            {"learning_preferences": preferences.dict(exclude_none=True)}
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update preferences"
            )
        
        # Get updated progress
        progress = await user_service.get_onboarding_progress(current_user.user_id)
        
        return {
            "message": "Preferences updated successfully",
            "progress": progress
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Onboarding preferences error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update onboarding preferences"
        )


@router.post("/onboarding/assessment")
async def submit_initial_assessment(
    assessment: InitialAssessment,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Submit initial assessment during onboarding
    
    Processes initial assessment and determines skill level.
    """
    try:
        user_service = UserService(db)
        
        # Process assessment and determine skill level
        assessment_result = await user_service.process_initial_assessment(
            current_user.user_id,
            assessment.dict()
        )
        
        # Complete assessment step
        success = await user_service.complete_onboarding_step(
            current_user.user_id,
            "assessment",
            assessment_result
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to process assessment"
            )
        
        # Get updated progress
        progress = await user_service.get_onboarding_progress(current_user.user_id)
        
        return {
            "message": "Assessment completed successfully",
            "skill_level": assessment_result["skill_level"],
            "progress": progress
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Initial assessment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process initial assessment"
        )


@router.post("/onboarding/dashboard-setup")
async def setup_dashboard_personalization(
    dashboard_config: DashboardPersonalization,
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Setup dashboard personalization during onboarding
    
    Configures user's dashboard preferences and layout.
    """
    try:
        user_service = UserService(db)
        
        # Save dashboard configuration
        success = await user_service.complete_onboarding_step(
            current_user.user_id,
            "dashboard_setup",
            {"dashboard_config": dashboard_config.dict()}
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to setup dashboard"
            )
        
        # Get updated progress
        progress = await user_service.get_onboarding_progress(current_user.user_id)
        
        return {
            "message": "Dashboard setup completed successfully",
            "progress": progress
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard setup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to setup dashboard"
        )


@router.post("/onboarding/complete")
async def complete_onboarding(
    current_user: UserProfile = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Complete the onboarding process
    
    Finalizes onboarding and marks user as fully onboarded.
    """
    try:
        user_service = UserService(db)
        
        # Check if all required steps are completed
        progress = await user_service.get_onboarding_progress(current_user.user_id)
        
        if progress["progress_percentage"] < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot complete onboarding. Some steps are still pending."
            )
        
        # Mark onboarding as completed
        success = await user_service.complete_onboarding(current_user.user_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to complete onboarding"
            )
        
        # Clear cache to refresh user data
        await user_service.clear_user_cache(current_user.user_id)
        
        return {
            "message": "Onboarding completed successfully",
            "onboarding_completed": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete onboarding error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete onboarding"
        )