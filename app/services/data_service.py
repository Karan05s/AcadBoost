"""
Data Collection Service
Handles student performance data collection and processing
"""
from typing import Dict, Any, List
from app.core.database import get_database
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DataCollectionService:
    """Service for collecting and processing student performance data"""
    
    def __init__(self):
        self.collection_name = "student_performance"
    
    async def store_quiz_submission(self, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """Store quiz submission data"""
        db = await get_database()
        collection = db[self.collection_name]
        
        # Add timestamp and submission type
        submission_data["timestamp"] = datetime.utcnow()
        submission_data["submission_type"] = "quiz"
        
        result = await collection.insert_one(submission_data)
        submission_data["_id"] = str(result.inserted_id)
        
        logger.info(f"Stored quiz submission for student: {submission_data.get('student_id')}")
        return submission_data
    
    async def store_code_submission(self, submission_data: Dict[str, Any]) -> Dict[str, Any]:
        """Store code submission data"""
        db = await get_database()
        collection = db[self.collection_name]
        
        # Add timestamp and submission type
        submission_data["timestamp"] = datetime.utcnow()
        submission_data["submission_type"] = "code"
        
        result = await collection.insert_one(submission_data)
        submission_data["_id"] = str(result.inserted_id)
        
        logger.info(f"Stored code submission for student: {submission_data.get('student_id')}")
        return submission_data
    
    async def get_student_performance(self, student_id: str) -> List[Dict[str, Any]]:
        """Get all performance data for a student"""
        db = await get_database()
        collection = db[self.collection_name]
        
        cursor = collection.find({"student_id": student_id}).sort("timestamp", -1)
        performance_data = []
        
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            performance_data.append(doc)
        
        return performance_data


# Create service instance
data_service = DataCollectionService()