"""
Data Collection API endpoints for quiz and code submissions
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any, Optional
import logging

from app.core.database import get_database
from app.services.data_collection_service import DataCollectionService
from app.models.performance import (
    QuizSubmissionRequest, CodeSubmissionRequest, SubmissionResponse,
    ValidationResponse, DataValidationError
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_data_service():
    """Dependency to get data collection service"""
    db = await get_database()
    return DataCollectionService(db)


@router.post("/quiz-submission", response_model=SubmissionResponse)
async def submit_quiz(
    submission: QuizSubmissionRequest,
    service: DataCollectionService = Depends(get_data_service)
):
    """
    Submit quiz results for processing and analysis
    
    Requirements: 1.1 - Automatically capture quiz results with question-level accuracy data
    """
    try:
        result = await service.process_quiz_submission(submission)
        return result
        
    except ValueError as e:
        # Handle validation errors
        logger.warning(f"Quiz submission validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error processing quiz submission: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process quiz submission"
        )


@router.post("/code-submission", response_model=SubmissionResponse)
async def submit_code(
    submission: CodeSubmissionRequest,
    service: DataCollectionService = Depends(get_data_service)
):
    """
    Submit code for analysis and performance tracking
    
    Requirements: 1.2 - Analyze code submission for correctness, efficiency, and concept understanding
    """
    try:
        result = await service.process_code_submission(submission)
        return result
        
    except ValueError as e:
        # Handle validation errors
        logger.warning(f"Code submission validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error processing code submission: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process code submission"
        )


@router.get("/student/{student_id}/performance", response_model=List[Dict[str, Any]])
async def get_student_performance(
    student_id: str,
    course_id: Optional[str] = None,
    service: DataCollectionService = Depends(get_data_service)
):
    """
    Retrieve performance data for a specific student
    
    Requirements: 1.3 - Timestamp all entries and associate with correct student profile
    """
    try:
        performance_data = await service.get_student_performance(student_id, course_id)
        return performance_data
        
    except Exception as e:
        logger.error(f"Error retrieving performance data for student {student_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance data"
        )


@router.put("/performance/{submission_id}")
async def update_submission(
    submission_id: str,
    updates: Dict[str, Any],
    service: DataCollectionService = Depends(get_data_service)
):
    """
    Update an existing performance submission
    
    Requirements: 1.4 - Handle missing or corrupted submissions gracefully
    """
    try:
        # Validate data integrity before update
        integrity_report = await service.validate_data_integrity(updates)
        
        if not integrity_report["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Data integrity validation failed: {integrity_report['errors']}"
            )
        
        success = await service.update_submission(submission_id, updates)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found"
            )
        
        response = {
            "success": True,
            "message": "Submission updated successfully",
            "submission_id": submission_id
        }
        
        # Include warnings if any data was corrected
        if integrity_report["warnings"]:
            response["warnings"] = integrity_report["warnings"]
            response["corrected_fields"] = integrity_report["corrected_fields"]
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating submission {submission_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update submission"
        )


@router.post("/validate-integrity")
async def validate_submission_integrity(
    submission_data: Dict[str, Any],
    service: DataCollectionService = Depends(get_data_service)
):
    """
    Validate data integrity for submission data
    
    Requirements: 1.4 - Validate data integrity and handle corrupted submissions
    """
    try:
        integrity_report = await service.validate_data_integrity(submission_data)
        return integrity_report
        
    except Exception as e:
        logger.error(f"Error validating data integrity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate data integrity"
        )


@router.get("/performance/stats/{student_id}")
async def get_performance_stats(
    student_id: str,
    course_id: Optional[str] = None,
    service: DataCollectionService = Depends(get_data_service)
):
    """
    Get performance statistics for a student
    
    Requirements: 1.3 - Performance data analysis and reporting
    """
    try:
        performance_data = await service.get_student_performance(student_id, course_id)
        
        if not performance_data:
            return {
                "student_id": student_id,
                "total_submissions": 0,
                "average_score": 0,
                "quiz_count": 0,
                "code_count": 0,
                "recent_activity": None
            }
        
        # Calculate statistics
        total_submissions = len(performance_data)
        quiz_submissions = [p for p in performance_data if p.get("submission_type") == "quiz"]
        code_submissions = [p for p in performance_data if p.get("submission_type") == "code"]
        
        # Calculate average score
        total_score = sum(p.get("score", 0) for p in performance_data)
        total_max_score = sum(p.get("max_score", 1) for p in performance_data)
        average_score = (total_score / total_max_score * 100) if total_max_score > 0 else 0
        
        # Get recent activity
        recent_activity = performance_data[0] if performance_data else None
        if recent_activity and "_id" in recent_activity:
            recent_activity["_id"] = str(recent_activity["_id"])
        
        return {
            "student_id": student_id,
            "total_submissions": total_submissions,
            "average_score": round(average_score, 2),
            "quiz_count": len(quiz_submissions),
            "code_count": len(code_submissions),
            "recent_activity": recent_activity
        }
        
    except Exception as e:
        logger.error(f"Error calculating performance stats for student {student_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate performance statistics"
        )