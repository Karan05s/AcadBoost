"""
Recommendation system data models
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class RecommendationType(str, Enum):
    """Types of recommendations"""
    LEARNING_RESOURCE = "learning_resource"
    PRACTICE_EXERCISE = "practice_exercise"
    CONCEPT_REVIEW = "concept_review"
    SKILL_BUILDING = "skill_building"
    ASSESSMENT = "assessment"


class LearningStyle(str, Enum):
    """Learning style preferences"""
    VISUAL = "visual"
    AUDITORY = "auditory"
    KINESTHETIC = "kinesthetic"
    READING_WRITING = "reading_writing"


class DifficultyLevel(str, Enum):
    """Difficulty levels for recommendations"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ResourceType(str, Enum):
    """Types of learning resources"""
    VIDEO = "video"
    ARTICLE = "article"
    INTERACTIVE = "interactive"
    QUIZ = "quiz"
    PROJECT = "project"
    TUTORIAL = "tutorial"
    BOOK = "book"
    COURSE = "course"


class LearningResource(BaseModel):
    """Learning resource model"""
    resource_id: str = Field(..., description="Unique resource identifier")
    title: str = Field(..., description="Resource title")
    description: str = Field(..., description="Resource description")
    resource_type: ResourceType = Field(..., description="Type of resource")
    difficulty_level: DifficultyLevel = Field(..., description="Difficulty level")
    concepts: List[str] = Field(default_factory=list, description="Concepts covered")
    prerequisites: List[str] = Field(default_factory=list, description="Required prerequisites")
    estimated_duration: int = Field(..., description="Estimated completion time in minutes")
    url: Optional[str] = Field(None, description="Resource URL")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class RecommendationRequest(BaseModel):
    """Request for personalized recommendations"""
    student_id: str = Field(..., description="Student identifier")
    course_id: Optional[str] = Field(None, description="Course context")
    gap_concepts: List[str] = Field(default_factory=list, description="Identified knowledge gaps")
    learning_style: Optional[LearningStyle] = Field(None, description="Preferred learning style")
    difficulty_preference: Optional[DifficultyLevel] = Field(None, description="Preferred difficulty")
    time_available: Optional[int] = Field(None, description="Available study time in minutes")
    resource_types: List[ResourceType] = Field(default_factory=list, description="Preferred resource types")
    exclude_completed: bool = Field(True, description="Exclude already completed resources")


class Recommendation(BaseModel):
    """Individual recommendation"""
    recommendation_id: str = Field(..., description="Unique recommendation identifier")
    student_id: str = Field(..., description="Target student")
    resource: LearningResource = Field(..., description="Recommended resource")
    recommendation_type: RecommendationType = Field(..., description="Type of recommendation")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in recommendation")
    priority_score: float = Field(..., ge=0.0, le=1.0, description="Priority/urgency score")
    reasoning: str = Field(..., description="Explanation for recommendation")
    target_concepts: List[str] = Field(default_factory=list, description="Concepts this addresses")
    prerequisites_met: bool = Field(..., description="Whether prerequisites are satisfied")
    estimated_impact: float = Field(..., ge=0.0, le=1.0, description="Expected learning impact")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")


class RecommendationResponse(BaseModel):
    """Response containing personalized recommendations"""
    student_id: str = Field(..., description="Student identifier")
    recommendations: List[Recommendation] = Field(..., description="List of recommendations")
    total_count: int = Field(..., description="Total number of recommendations")
    generation_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Generation time")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional response metadata")


class LearningPath(BaseModel):
    """Structured learning path with ordered recommendations"""
    path_id: str = Field(..., description="Unique path identifier")
    student_id: str = Field(..., description="Target student")
    title: str = Field(..., description="Learning path title")
    description: str = Field(..., description="Path description")
    target_concepts: List[str] = Field(..., description="Concepts covered in this path")
    recommendations: List[Recommendation] = Field(..., description="Ordered recommendations")
    estimated_duration: int = Field(..., description="Total estimated duration in minutes")
    difficulty_progression: List[DifficultyLevel] = Field(..., description="Difficulty progression")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class RecommendationFeedback(BaseModel):
    """Feedback on recommendation effectiveness"""
    feedback_id: str = Field(..., description="Unique feedback identifier")
    recommendation_id: str = Field(..., description="Related recommendation")
    student_id: str = Field(..., description="Student providing feedback")
    completed: bool = Field(..., description="Whether recommendation was completed")
    effectiveness_rating: Optional[int] = Field(None, ge=1, le=5, description="Effectiveness rating (1-5)")
    difficulty_rating: Optional[int] = Field(None, ge=1, le=5, description="Difficulty rating (1-5)")
    time_spent: Optional[int] = Field(None, description="Actual time spent in minutes")
    helpful: Optional[bool] = Field(None, description="Whether recommendation was helpful")
    comments: Optional[str] = Field(None, description="Additional feedback comments")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Feedback timestamp")


class RecommendationMetrics(BaseModel):
    """Metrics for recommendation performance"""
    recommendation_id: str = Field(..., description="Recommendation identifier")
    student_id: str = Field(..., description="Student identifier")
    click_through_rate: float = Field(0.0, ge=0.0, le=1.0, description="Click-through rate")
    completion_rate: float = Field(0.0, ge=0.0, le=1.0, description="Completion rate")
    average_rating: Optional[float] = Field(None, ge=1.0, le=5.0, description="Average effectiveness rating")
    total_interactions: int = Field(0, description="Total number of interactions")
    successful_completions: int = Field(0, description="Number of successful completions")
    average_time_to_complete: Optional[float] = Field(None, description="Average completion time")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last metrics update")


class StudentPreferences(BaseModel):
    """Student learning preferences for personalization"""
    student_id: str = Field(..., description="Student identifier")
    learning_style: Optional[LearningStyle] = Field(None, description="Preferred learning style")
    difficulty_preference: DifficultyLevel = Field(DifficultyLevel.INTERMEDIATE, description="Preferred difficulty")
    preferred_resource_types: List[ResourceType] = Field(default_factory=list, description="Preferred resource types")
    study_time_preference: Optional[int] = Field(None, description="Preferred study session length in minutes")
    notification_preferences: Dict[str, bool] = Field(default_factory=dict, description="Notification settings")
    accessibility_needs: List[str] = Field(default_factory=list, description="Accessibility requirements")
    language_preference: str = Field("en", description="Preferred language code")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")