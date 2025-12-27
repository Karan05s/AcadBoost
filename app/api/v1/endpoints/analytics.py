"""
Analytics and gap analysis endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from app.services.dashboard_service import dashboard_service
from app.services.notification_service import notification_service
from app.services.analytics_service import analytics_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/gaps/{student_id}")
async def get_learning_gaps(student_id: str):
    """Get learning gaps for student"""
    try:
        gaps = await analytics_service.analyze_learning_gaps(student_id)
        return {
            "student_id": student_id,
            "gaps": gaps,
            "total_gaps": len(gaps)
        }
    except Exception as e:
        logger.error(f"Error getting learning gaps for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve learning gaps")


@router.get("/dashboard/{student_id}")
async def get_dashboard_data(student_id: str):
    """Get optimized dashboard analytics data with progress trends and achievements"""
    try:
        dashboard_data = await dashboard_service.get_optimized_dashboard_data(student_id)
        return dashboard_data
    except Exception as e:
        logger.error(f"Error getting dashboard data for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard data")


@router.get("/progress-trends/{student_id}")
async def get_progress_trends(student_id: str):
    """Get detailed progress trends for student"""
    try:
        dashboard_data = await dashboard_service.get_optimized_dashboard_data(student_id)
        return {
            "student_id": student_id,
            "progress_trends": dashboard_data.get("progress_trends", {}),
            "visual_indicators": dashboard_data.get("visual_indicators", {})
        }
    except Exception as e:
        logger.error(f"Error getting progress trends for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve progress trends")


@router.get("/achievements/{student_id}")
async def get_achievements(student_id: str):
    """Get achievements and milestones for student"""
    try:
        dashboard_data = await dashboard_service.get_optimized_dashboard_data(student_id)
        return {
            "student_id": student_id,
            "achievements": dashboard_data.get("achievements", {})
        }
    except Exception as e:
        logger.error(f"Error getting achievements for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve achievements")


@router.get("/notifications/{student_id}")
async def get_notifications(student_id: str):
    """Get all notifications for student"""
    try:
        notifications = await notification_service.get_all_notifications(student_id)
        return notifications
    except Exception as e:
        logger.error(f"Error getting notifications for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve notifications")


@router.get("/notifications/{student_id}/achievements")
async def get_achievement_notifications(student_id: str):
    """Get achievement notifications for student"""
    try:
        achievements = await notification_service.generate_achievement_notifications(student_id)
        return {
            "student_id": student_id,
            "achievements": achievements,
            "count": len(achievements)
        }
    except Exception as e:
        logger.error(f"Error getting achievement notifications for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve achievement notifications")


@router.get("/notifications/{student_id}/milestones")
async def get_milestone_alerts(student_id: str):
    """Get progress milestone alerts for student"""
    try:
        milestones = await notification_service.generate_progress_milestone_alerts(student_id)
        return {
            "student_id": student_id,
            "milestones": milestones,
            "count": len(milestones)
        }
    except Exception as e:
        logger.error(f"Error getting milestone alerts for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve milestone alerts")


@router.get("/notifications/{student_id}/suggestions")
async def get_strategy_suggestions(student_id: str):
    """Get alternative strategy suggestions for student"""
    try:
        suggestions = await notification_service.generate_alternative_strategy_suggestions(student_id)
        return {
            "student_id": student_id,
            "suggestions": suggestions,
            "count": len(suggestions)
        }
    except Exception as e:
        logger.error(f"Error getting strategy suggestions for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve strategy suggestions")


@router.put("/notifications/{student_id}/preferences")
async def update_notification_preferences(student_id: str, preferences: Dict[str, Any]):
    """Update notification preferences for student"""
    try:
        success = await notification_service.handle_notification_preferences(student_id, preferences)
        if success:
            return {
                "message": "Notification preferences updated successfully",
                "student_id": student_id,
                "preferences": preferences
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update notification preferences")
    except Exception as e:
        logger.error(f"Error updating notification preferences for {student_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update notification preferences")