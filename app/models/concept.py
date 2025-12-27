"""
Concept mapping and knowledge base models
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class ConceptDifficulty(str, Enum):
    """Difficulty levels for learning concepts"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ConceptType(str, Enum):
    """Types of learning concepts"""
    FUNDAMENTAL = "fundamental"
    PROCEDURAL = "procedural"
    CONCEPTUAL = "conceptual"
    METACOGNITIVE = "metacognitive"


class LearningConcept(BaseModel):
    """Model for individual learning concepts"""
    concept_id: str = Field(..., description="Unique identifier for the concept")
    name: str = Field(..., description="Human-readable name of the concept")
    description: str = Field(..., description="Detailed description of the concept")
    concept_type: ConceptType = Field(..., description="Type of learning concept")
    difficulty_level: ConceptDifficulty = Field(..., description="Difficulty level")
    prerequisites: List[str] = Field(default=[], description="List of prerequisite concept IDs")
    related_concepts: List[str] = Field(default=[], description="List of related concept IDs")
    keywords: List[str] = Field(default=[], description="Keywords associated with the concept")
    subject_area: str = Field(..., description="Subject area (e.g., 'computer_science', 'mathematics')")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConceptMapping(BaseModel):
    """Model for mapping questions/problems to concepts"""
    mapping_id: str = Field(..., description="Unique identifier for the mapping")
    question_id: str = Field(..., description="ID of the question or problem")
    concept_id: str = Field(..., description="ID of the mapped concept")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in the mapping")
    mapping_type: str = Field(..., description="Type of mapping (e.g., 'direct', 'inferred', 'prerequisite')")
    evidence: Dict[str, Any] = Field(default={}, description="Evidence supporting the mapping")
    created_by: str = Field(..., description="Who/what created this mapping")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    validated: bool = Field(default=False, description="Whether the mapping has been validated")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConceptAssessment(BaseModel):
    """Model for assessing student understanding of concepts"""
    assessment_id: str = Field(..., description="Unique identifier for the assessment")
    student_id: str = Field(..., description="ID of the student")
    concept_id: str = Field(..., description="ID of the assessed concept")
    mastery_level: float = Field(..., ge=0.0, le=1.0, description="Level of concept mastery")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in the assessment")
    evidence_submissions: List[str] = Field(default=[], description="List of submission IDs used as evidence")
    assessment_method: str = Field(..., description="Method used for assessment")
    assessed_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConceptRelationship(BaseModel):
    """Model for relationships between concepts"""
    relationship_id: str = Field(..., description="Unique identifier for the relationship")
    source_concept_id: str = Field(..., description="ID of the source concept")
    target_concept_id: str = Field(..., description="ID of the target concept")
    relationship_type: str = Field(..., description="Type of relationship (e.g., 'prerequisite', 'builds_on', 'related')")
    strength: float = Field(..., ge=0.0, le=1.0, description="Strength of the relationship")
    bidirectional: bool = Field(default=False, description="Whether the relationship is bidirectional")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConceptMappingRequest(BaseModel):
    """Request model for concept mapping"""
    question_id: str = Field(..., description="ID of the question to map")
    question_text: str = Field(..., description="Text content of the question")
    question_type: str = Field(..., description="Type of question (e.g., 'multiple_choice', 'coding', 'essay')")
    subject_area: str = Field(..., description="Subject area of the question")
    difficulty_hint: Optional[ConceptDifficulty] = Field(None, description="Hint about question difficulty")
    existing_tags: List[str] = Field(default=[], description="Existing tags or keywords")
    context: Dict[str, Any] = Field(default={}, description="Additional context for mapping")


class ConceptMappingResponse(BaseModel):
    """Response model for concept mapping"""
    question_id: str = Field(..., description="ID of the mapped question")
    mapped_concepts: List[ConceptMapping] = Field(..., description="List of mapped concepts")
    primary_concept: Optional[str] = Field(None, description="ID of the primary concept")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Overall confidence in the mapping")
    mapping_method: str = Field(..., description="Method used for mapping")
    suggestions: List[str] = Field(default=[], description="Suggested improvements or alternatives")


class CodeConceptAssessment(BaseModel):
    """Model for assessing programming concepts in code submissions"""
    assessment_id: str = Field(..., description="Unique identifier for the assessment")
    submission_id: str = Field(..., description="ID of the code submission")
    student_id: str = Field(..., description="ID of the student")
    programming_concepts: Dict[str, float] = Field(..., description="Map of concept IDs to mastery scores")
    algorithm_concepts: Dict[str, float] = Field(default={}, description="Algorithm-specific concepts")
    best_practices: Dict[str, float] = Field(default={}, description="Best practice adherence scores")
    code_quality_metrics: Dict[str, Any] = Field(default={}, description="Code quality indicators")
    assessed_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConceptKnowledgeBase(BaseModel):
    """Model for the concept knowledge base"""
    kb_id: str = Field(..., description="Unique identifier for the knowledge base")
    name: str = Field(..., description="Name of the knowledge base")
    description: str = Field(..., description="Description of the knowledge base")
    version: str = Field(..., description="Version of the knowledge base")
    subject_areas: List[str] = Field(..., description="List of covered subject areas")
    total_concepts: int = Field(..., description="Total number of concepts")
    total_relationships: int = Field(..., description="Total number of relationships")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }