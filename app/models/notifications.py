"""
Notification data models
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class NotificationType(str, Enum):
    ACHIEVEMENT = "achievement"
    MILESTONE = "milestone"
    STRATEGY_SUGGESTION = "strategy_suggestion"
    REMINDER = "reminder"
    ALERT = "alert"


class NotificationPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NotificationSubtype(str, Enum):
    # Achievement subtypes
    BADGE_EARNED = "badge_earned"
    PERFECT_SCORE = "perfect_score"
    IMPROVEMENT_STREAK = "improvement_streak"
    CONCEPT_MASTERY = "concept_mastery"
    
    # Milestone subtypes
    SUBMISSIONS = "submissions"
    WEEKLY_ACTIVITY = "weekly_activity"
    
    # Strategy suggestion subtypes
    PERSISTENT_GAP = "persistent_gap"
    LEARNING_STYLE_MISMATCH = "learning_style_mismatch"
    STUDY_PATTERN = "study_pattern"


class Notification(BaseModel):
    type: NotificationType
    subtype: Optional[NotificationSubtype] = None
    title: str
    message: str
    priority: NotificationPriority
    created_at: datetime
    read: bool = False
    data: Optional[Dict[str, Any]] = None


class NotificationPreferencesUpdate(BaseModel):
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    achievement_alerts: Optional[bool] = None
    reminder_frequency: Optional[str] = None  # "daily" | "weekly" | "never"


class AchievementNotification(BaseModel):
    type: str = "achievement"
    achievement_type: str  # "badge", "perfect_score", "streak", "mastery"
    title: str
    description: str
    icon: Optional[str] = None
    earned_at: datetime
    data: Optional[Dict[str, Any]] = None


class MilestoneAlert(BaseModel):
    type: str = "milestone"
    milestone_type: str  # "submissions", "mastery", "activity"
    milestone_value: int
    title: str
    description: str
    achieved_at: datetime
    data: Optional[Dict[str, Any]] = None


class StrategySuggestion(BaseModel):
    type: str = "strategy_suggestion"
    strategy_type: str  # "resource_change", "study_pattern", "social_learning"
    concept_id: Optional[str] = None
    title: str
    description: str
    recommended_action: str
    priority: NotificationPriority
    data: Optional[Dict[str, Any]] = None


class NotificationSummary(BaseModel):
    total_count: int
    unread_count: int
    notifications: List[Notification]
    categories: Dict[str, int]
    generated_at: datetime


class Badge(BaseModel):
    badge_type: str
    name: str
    description: str
    icon: str
    earned_at: datetime
    student_id: str


class Achievement(BaseModel):
    achievement_id: str
    student_id: str
    type: str
    title: str
    description: str
    earned_at: datetime
    data: Optional[Dict[str, Any]] = None


class ProgressTrend(BaseModel):
    trend_direction: str  # "improving", "declining", "stable", "no_data"
    trend_strength: float  # 0.0 to 1.0
    weekly_progress: List[Dict[str, Any]]
    concept_progress: Dict[str, Any]
    improvement_rate: float
    data_points: int
    period_start: datetime
    period_end: datetime


class VisualIndicator(BaseModel):
    progress_chart_data: List[Dict[str, Any]]
    concept_mastery_chart: Dict[str, Any]
    achievement_timeline: List[Dict[str, Any]]
    performance_heatmap: Dict[str, Any]
    trend_indicators: Dict[str, Any]