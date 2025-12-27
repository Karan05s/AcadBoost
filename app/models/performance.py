"""
Performance data models for quiz and code submissions
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class SubmissionType(str, Enum):
    QUIZ = "quiz"
    CODE = "code"


class QuestionResponse(BaseModel):
    """Individual question response in a quiz"""
    question_id: str
    response: str
    correct: bool
    concept_tags: List[str] = Field(default_factory=list)
    time_spent: Optional[int] = None  # seconds


class CodeMetrics(BaseModel):
    """Code submission analysis metrics"""
    complexity: Optional[int] = None
    test_coverage: Optional[float] = None
    execution_time: Optional[float] = None  # milliseconds
    memory_usage: Optional[int] = None  # bytes
    syntax_errors: int = 0
    runtime_errors: int = 0
    passed_tests: int = 0
    total_tests: int = 0


class PerformanceData(BaseModel):
    """Stored performance data model"""
    submission_id: str = Field(..., description="Unique identifier for the submission")
    student_id: str
    submission_type: SubmissionType
    course_id: str
    assignment_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    score: float
    max_score: float
    question_responses: Optional[List[QuestionResponse]] = None
    code_metrics: Optional[CodeMetrics] = None
    processed: bool = Field(default=False)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PerformanceSubmission(BaseModel):
    """Base model for performance data submissions"""
    student_id: str
    submission_type: SubmissionType
    course_id: str
    assignment_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    score: float
    max_score: float
    
    # Quiz-specific fields
    question_responses: Optional[List[QuestionResponse]] = None
    
    # Code-specific fields
    code_content: Optional[str] = None
    code_metrics: Optional[CodeMetrics] = None
    
    # Common metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QuizSubmissionRequest(BaseModel):
    """Request model for quiz submissions"""
    student_id: str
    course_id: str
    assignment_id: str
    question_responses: List[QuestionResponse]
    total_time_spent: Optional[int] = None  # seconds


class CodeSubmissionRequest(BaseModel):
    """Request model for code submissions"""
    student_id: str
    course_id: str
    assignment_id: str
    code_content: str
    language: str = "python"
    test_results: Optional[Dict[str, Any]] = None


class SubmissionResponse(BaseModel):
    """Response model for successful submissions"""
    submission_id: str
    student_id: str
    submission_type: SubmissionType
    score: float
    max_score: float
    timestamp: datetime
    processing_status: str = "completed"
    message: str = "Submission processed successfully"


class DataValidationError(BaseModel):
    """Model for data validation errors"""
    field: str
    error: str
    value: Any


class ValidationResponse(BaseModel):
    """Response model for validation errors"""
    success: bool = False
    errors: List[DataValidationError]
    message: str = "Data validation failed"


class LearningGap(BaseModel):
    """Model for identified learning gaps"""
    gap_id: str = Field(..., description="Unique identifier for the gap")
    student_id: str = Field(..., description="ID of the student")
    concept_id: str = Field(..., description="ID of the concept with the gap")
    gap_severity: float = Field(..., ge=0.0, le=1.0, description="Severity of the gap (0-1)")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in gap detection")
    identified_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    supporting_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    improvement_trend: float = Field(default=0.0, description="Trend in gap improvement (-1 to 1)")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class GapAnalysisRequest(BaseModel):
    """Request model for gap analysis"""
    student_id: str
    time_window_days: int = 30
    include_confidence_intervals: bool = True
    concept_filter: Optional[List[str]] = None


class GapAnalysisResponse(BaseModel):
    """Response model for gap analysis"""
    student_id: str
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)
    identified_gaps: List[LearningGap]
    total_gaps: int
    average_severity: float
    confidence_intervals: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    recommendations_generated: bool = False
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }