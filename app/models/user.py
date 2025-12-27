"""
User data models
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


class LearningStyle(str, Enum):
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    MIXED = "mixed"


class StudyTimePreference(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    FLEXIBLE = "flexible"


class DifficultyPreference(str, Enum):
    GRADUAL = "gradual"
    CHALLENGING = "challenging"
    ADAPTIVE = "adaptive"


class AcademicYear(str, Enum):
    FRESHMAN = "freshman"
    SOPHOMORE = "sophomore"
    JUNIOR = "junior"
    SENIOR = "senior"
    GRADUATE = "graduate"


class NotificationPreferences(BaseModel):
    email_notifications: bool = True
    push_notifications: bool = True
    achievement_alerts: bool = True
    reminder_frequency: str = "weekly"  # "daily" | "weekly" | "never"


class LearningPreferences(BaseModel):
    learning_style: Optional[LearningStyle] = None
    study_time_preference: Optional[StudyTimePreference] = None
    difficulty_preference: Optional[DifficultyPreference] = None
    resource_preferences: Optional[List[str]] = None  # ["video", "text", "interactive", "practice"]
    notification_preferences: Optional[NotificationPreferences] = None


class AcademicInfo(BaseModel):
    major: Optional[str] = None
    year: Optional[AcademicYear] = None
    gpa: Optional[float] = None
    enrolled_courses: Optional[List[str]] = None


class UserProfile(BaseModel):
    user_id: str
    email: EmailStr
    username: str
    first_name: str
    last_name: str
    role: UserRole
    institution: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None
    email_verified: bool = False
    profile_completed: bool = False
    onboarding_completed: bool = False
    learning_preferences: Optional[LearningPreferences] = None
    academic_info: Optional[AcademicInfo] = None


class UserRegistration(BaseModel):
    email: EmailStr
    username: str
    password: str
    first_name: str
    last_name: str
    role: UserRole
    institution: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    institution: Optional[str] = None
    learning_preferences: Optional[LearningPreferences] = None
    academic_info: Optional[AcademicInfo] = None


# Onboarding Models

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