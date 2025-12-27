"""
Gap Analysis API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from app.core.database import get_database
from app.models.performance import GapAnalysisRequest, GapAnalysisResponse, LearningGap
from app.services.realtime_gap_analysis_service import RealtimeGapAnalysisService
from app.services.gap_detection_service import GapDetectionService
from app.core.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/analyze/{student_id}", response_model=GapAnalysisResponse)
async def analyze_student_gaps(
    student_id: str,
    request: Optional[GapAnalysisRequest] = None,
    urgent: bool = False,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Analyze learning gaps for a specific student
    """
    try:
        # Initialize services
        realtime_service = RealtimeGapAnalysisService(db)
        await realtime_service.initialize()
        
        if urgent:
            # Perform immediate analysis
            response = await realtime_service.trigger_urgent_analysis(
                student_id, 
                reason="api_urgent_request"
            )
        else:
            # Use existing analysis or trigger background update
            gap_detection_service = GapDetectionService(db)
            await gap_detection_service.initialize_models()
            
            gaps = await gap_detection_service.detect_learning_gaps(student_id)
            
            # Calculate statistics
            total_gaps = len(gaps)
            average_severity = sum(gap.gap_severity for gap in gaps) / total_gaps if total_gaps > 0 else 0.0
            
            # Calculate confidence intervals
            confidence_intervals = {}
            for gap in gaps:
                intervals = await gap_detection_service.calculate_confidence_intervals(
                    student_id, gap.concept_id
                )
                confidence_intervals[gap.concept_id] = intervals
            
            response = GapAnalysisResponse(
                student_id=student_id,
                identified_gaps=gaps,
                total_gaps=total_gaps,
                average_severity=average_severity,
                confidence_intervals=confidence_intervals
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Error analyzing student gaps: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/student/{student_id}/gaps", response_model=List[LearningGap])
async def get_student_gaps(
    student_id: str,
    include_resolved: bool = False,
    severity_threshold: float = 0.0,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Get current learning gaps for a student
    """
    try:
        # Build query filter
        query_filter = {"student_id": student_id}
        
        if not include_resolved:
            query_filter["gap_severity"] = {"$gt": 0.1}  # Exclude very low severity gaps
        
        if severity_threshold > 0:
            query_filter["gap_severity"] = {"$gte": severity_threshold}
        
        # Get gaps from database
        gap_docs = await db.learning_gaps.find(query_filter).sort("gap_severity", -1).to_list(None)
        
        gaps = [LearningGap(**doc) for doc in gap_docs]
        
        return gaps
        
    except Exception as e:
        logger.error(f"Error getting student gaps: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/student/{student_id}/history", response_model=List[GapAnalysisResponse])
async def get_analysis_history(
    student_id: str,
    limit: int = 10,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Get historical gap analysis results for a student
    """
    try:
        realtime_service = RealtimeGapAnalysisService(db)
        history = await realtime_service.get_analysis_history(student_id, limit)
        
        return history
        
    except Exception as e:
        logger.error(f"Error getting analysis history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger/{student_id}")
async def trigger_gap_analysis(
    student_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Trigger background gap analysis for a student
    """
    try:
        realtime_service = RealtimeGapAnalysisService(db)
        await realtime_service.initialize()
        
        # Add to background processing
        background_tasks.add_task(
            realtime_service.trigger_gap_analysis,
            student_id,
            {"trigger_source": "api_request"}
        )
        
        return {"message": f"Gap analysis triggered for student {student_id}"}
        
    except Exception as e:
        logger.error(f"Error triggering gap analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/concept/{concept_id}/students")
async def get_students_with_concept_gap(
    concept_id: str,
    severity_threshold: float = 0.3,
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Get students who have gaps in a specific concept
    """
    try:
        gap_docs = await db.learning_gaps.find({
            "concept_id": concept_id,
            "gap_severity": {"$gte": severity_threshold}
        }).sort("gap_severity", -1).to_list(None)
        
        students = []
        for gap_doc in gap_docs:
            students.append({
                "student_id": gap_doc["student_id"],
                "gap_severity": gap_doc["gap_severity"],
                "confidence_score": gap_doc["confidence_score"],
                "identified_at": gap_doc["identified_at"],
                "improvement_trend": gap_doc.get("improvement_trend", 0.0)
            })
        
        return {
            "concept_id": concept_id,
            "students_with_gaps": students,
            "total_students": len(students)
        }
        
    except Exception as e:
        logger.error(f"Error getting students with concept gap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/status")
async def get_system_status(
    db=Depends(get_database),
    current_user=Depends(get_current_user)
):
    """
    Get gap analysis system status
    """
    try:
        realtime_service = RealtimeGapAnalysisService(db)
        queue_status = await realtime_service.get_queue_status()
        
        # Get recent analysis statistics
        recent_analyses = await db.gap_analyses.count_documents({
            "analysis_timestamp": {"$gte": datetime.utcnow() - timedelta(hours=24)}
        })
        
        total_gaps = await db.learning_gaps.count_documents({})
        
        return {
            "queue_status": queue_status,
            "recent_analyses_24h": recent_analyses,
            "total_active_gaps": total_gaps,
            "system_healthy": queue_status.get("is_running", False)
        }
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))