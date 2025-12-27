"""
Recommendation Service
Handles personalized learning recommendations
"""
from typing import Dict, Any, List
from app.core.database import get_database
import logging

logger = logging.getLogger(__name__)


class RecommendationService:
    """Service for generating and managing personalized recommendations"""
    
    def __init__(self):
        self.collection_name = "recommendations"
    
    async def get_recommendations(self, student_id: str) -> List[Dict[str, Any]]:
        """Get personalized recommendations for a student"""
        db = await get_database()
        collection = db[self.collection_name]
        
        cursor = collection.find({"student_id": student_id}).sort("priority_score", -1)
        recommendations = []
        
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            recommendations.append(doc)
        
        return recommendations
    
    async def complete_recommendation(self, student_id: str, recommendation_id: str) -> bool:
        """Mark a recommendation as completed"""
        db = await get_database()
        collection = db[self.collection_name]
        
        result = await collection.update_one(
            {"_id": recommendation_id, "student_id": student_id},
            {"$set": {"completed": True}}
        )
        
        return result.modified_count > 0


# Create service instance
recommendation_service = RecommendationService()