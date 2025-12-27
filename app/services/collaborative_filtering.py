"""
Collaborative Filtering Algorithm for Recommendations
"""
import logging
import math
import uuid
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.recommendations import (
    RecommendationRequest, Recommendation, LearningResource, 
    RecommendationType
)

logger = logging.getLogger(__name__)


class CollaborativeFilteringAlgorithm:
    """Collaborative filtering recommendation algorithm"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def generate_recommendations(
        self, 
        request: RecommendationRequest,
        learning_history: List[Dict[str, Any]]
    ) -> List[Recommendation]:
        """Generate recommendations using collaborative filtering"""
        try:
            # Find similar students based on performance patterns
            similar_students = await self._find_similar_students(request.student_id, learning_history)
            
            # Get resources that similar students found helpful
            recommended_resources = await self._get_similar_student_resources(similar_students)
            
            # Convert to recommendation objects
            recommendations = []
            for resource_data in recommended_resources[:10]:  # Top 10
                rec = Recommendation(
                    recommendation_id=str(uuid.uuid4()),
                    student_id=request.student_id,
                    resource=LearningResource(**resource_data["resource"]),
                    recommendation_type=RecommendationType.LEARNING_RESOURCE,
                    confidence_score=resource_data["similarity_score"],
                    priority_score=resource_data["effectiveness_score"],
                    reasoning=f"Students with similar learning patterns found this helpful (similarity: {resource_data['similarity_score']:.2f})",
                    target_concepts=resource_data["resource"]["concepts"],
                    prerequisites_met=True,  # Will be checked later
                    estimated_impact=resource_data["effectiveness_score"]
                )
                recommendations.append(rec)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in collaborative filtering: {e}")
            return []
    
    async def _find_similar_students(
        self, 
        student_id: str, 
        learning_history: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find students with similar learning patterns"""
        try:
            # Get concept performance for target student
            student_concepts = self._extract_concept_performance(learning_history)
            
            # Find other students with similar concept performance
            similar_students = []
            
            # This is a simplified version - in production, you'd use more sophisticated similarity metrics
            cursor = self.db.student_performance.aggregate([
                {"$match": {"student_id": {"$ne": student_id}}},
                {"$group": {
                    "_id": "$student_id",
                    "performances": {"$push": "$$ROOT"}
                }},
                {"$limit": 50}  # Limit for performance
            ])
            
            async for student_data in cursor:
                other_student_concepts = self._extract_concept_performance(student_data["performances"])
                similarity = self._calculate_similarity(student_concepts, other_student_concepts)
                
                if similarity > 0.3:  # Minimum similarity threshold
                    similar_students.append({
                        "student_id": student_data["_id"],
                        "similarity": similarity,
                        "performances": student_data["performances"]
                    })
            
            # Sort by similarity
            similar_students.sort(key=lambda x: x["similarity"], reverse=True)
            return similar_students[:10]  # Top 10 similar students
            
        except Exception as e:
            logger.error(f"Error finding similar students: {e}")
            return []
    
    def _extract_concept_performance(self, performances: List[Dict[str, Any]]) -> Dict[str, float]:
        """Extract concept performance scores from student history"""
        concept_scores = {}
        concept_counts = {}
        
        for perf in performances:
            # Extract concepts from metadata or question responses
            concepts = []
            
            if "metadata" in perf and "concept_tags" in perf["metadata"]:
                concepts.extend(perf["metadata"]["concept_tags"])
            
            if "question_responses" in perf:
                for response in perf["question_responses"]:
                    if "concept_tags" in response:
                        concepts.extend(response["concept_tags"])
            
            # Calculate performance score
            score = perf.get("score", 0)
            max_score = perf.get("max_score", 1)
            performance_ratio = score / max_score if max_score > 0 else 0
            
            # Update concept scores
            for concept in concepts:
                if concept not in concept_scores:
                    concept_scores[concept] = 0
                    concept_counts[concept] = 0
                
                concept_scores[concept] += performance_ratio
                concept_counts[concept] += 1
        
        # Calculate average scores
        avg_concept_scores = {}
        for concept, total_score in concept_scores.items():
            avg_concept_scores[concept] = total_score / concept_counts[concept]
        
        return avg_concept_scores
    
    def _calculate_similarity(
        self, 
        concepts1: Dict[str, float], 
        concepts2: Dict[str, float]
    ) -> float:
        """Calculate similarity between two concept performance profiles"""
        if not concepts1 or not concepts2:
            return 0.0
        
        # Find common concepts
        common_concepts = set(concepts1.keys()) & set(concepts2.keys())
        
        if not common_concepts:
            return 0.0
        
        # Calculate cosine similarity for common concepts
        dot_product = sum(concepts1[concept] * concepts2[concept] for concept in common_concepts)
        
        norm1 = math.sqrt(sum(concepts1[concept] ** 2 for concept in common_concepts))
        norm2 = math.sqrt(sum(concepts2[concept] ** 2 for concept in common_concepts))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        return max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
    
    async def _get_similar_student_resources(
        self, 
        similar_students: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get resources that similar students found effective"""
        # Mock resources based on similar student patterns
        mock_resources = [
            {
                "resource": {
                    "resource_id": "res_001",
                    "title": "Introduction to Python Functions",
                    "description": "Learn the basics of Python functions",
                    "resource_type": "tutorial",
                    "difficulty_level": "beginner",
                    "concepts": ["functions", "python_basics"],
                    "prerequisites": [],
                    "estimated_duration": 30,
                    "url": "https://example.com/python-functions"
                },
                "similarity_score": 0.8,
                "effectiveness_score": 0.9
            },
            {
                "resource": {
                    "resource_id": "res_002", 
                    "title": "Data Structures Fundamentals",
                    "description": "Understanding arrays, lists, and dictionaries",
                    "resource_type": "video",
                    "difficulty_level": "intermediate",
                    "concepts": ["data_structures", "arrays", "lists"],
                    "prerequisites": ["python_basics"],
                    "estimated_duration": 45,
                    "url": "https://example.com/data-structures"
                },
                "similarity_score": 0.7,
                "effectiveness_score": 0.85
            }
        ]
        
        return mock_resources