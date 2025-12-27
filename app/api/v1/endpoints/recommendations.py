"""
Recommendation API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_database
from app.services.recommendation_engine_service import RecommendationEngineService
from app.models.recommendations import (
    RecommendationRequest, RecommendationResponse, LearningPath,
    RecommendationFeedback
)

router = APIRouter()


@router.post("/generate", response_model=RecommendationResponse)
async def generate_recommendations(
    request: RecommendationRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Generate personalized recommendations for a student
    
    Requirements: 3.1, 3.3 - Personalized recommendations based on gaps and preferences
    """
    try:
        recommendation_service = RecommendationEngineService(db)
        recommendations = await recommendation_service.generate_personalized_recommendations(request)
        return recommendations
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating recommendations: {str(e)}"
        )


@router.post("/learning-path", response_model=LearningPath)
async def generate_learning_path(
    student_id: str,
    target_concepts: List[str],
    max_duration: Optional[int] = None,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Generate a structured learning path with prerequisite ordering
    
    Requirements: 3.1 - Learning path generation with prerequisite ordering
    """
    try:
        recommendation_service = RecommendationEngineService(db)
        learning_path = await recommendation_service.generate_learning_path(
            student_id, target_concepts, max_duration
        )
        return learning_path
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating learning path: {str(e)}"
        )


@router.post("/feedback/{recommendation_id}")
async def submit_recommendation_feedback(
    recommendation_id: str,
    feedback: RecommendationFeedback,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Submit feedback on recommendation effectiveness
    
    Requirements: 5.4 - Recommendation effectiveness tracking
    """
    try:
        recommendation_service = RecommendationEngineService(db)
        success = await recommendation_service.update_recommendation_feedback(
            recommendation_id, feedback.dict()
        )
        
        if success:
            return {"message": "Feedback submitted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to submit feedback"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting feedback: {str(e)}"
        )


@router.get("/student/{student_id}")
async def get_student_recommendations(
    student_id: str,
    limit: int = 20,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get existing recommendations for a student
    """
    try:
        cursor = db.recommendations.find({"student_id": student_id}).sort("created_at", -1).limit(limit)
        recommendations = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string for JSON serialization
        for rec in recommendations:
            rec["_id"] = str(rec["_id"])
        
        return {"recommendations": recommendations}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving recommendations: {str(e)}"
        )


@router.get("/learning-paths/{student_id}")
async def get_student_learning_paths(
    student_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Get learning paths for a student
    """
    try:
        cursor = db.learning_paths.find({"student_id": student_id}).sort("created_at", -1)
        paths = await cursor.to_list(length=None)
        
        # Convert ObjectId to string for JSON serialization
        for path in paths:
            path["_id"] = str(path["_id"])
        
        return {"learning_paths": paths}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving learning paths: {str(e)}"
        )