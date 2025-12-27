"""
Content-Based Filtering Algorithm for Recommendations
"""
import logging
import uuid
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.recommendations import (
    RecommendationRequest, Recommendation, LearningResource, 
    RecommendationType, DifficultyLevel
)

logger = logging.getLogger(__name__)


class ContentBasedFilteringAlgorithm:
    """Content-based filtering recommendation algorithm"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def generate_recommendations(
        self, 
        request: RecommendationRequest,
        learning_history: List[Dict[str, Any]]
    ) -> List[Recommendation]:
        """Generate recommendations using content-based filtering"""
        try:
            # Find resources that match gap concepts
            matching_resources = await self._find_concept_matching_resources(request.gap_concepts)
            
            # Score resources based on student's learning patterns
            scored_resources = self._score_resources_by_patterns(matching_resources, learning_history)
            
            # Convert to recommendation objects
            recommendations = []
            for resource_data in scored_resources[:10]:  # Top 10
                rec = Recommendation(
                    recommendation_id=str(uuid.uuid4()),
                    student_id=request.student_id,
                    resource=LearningResource(**resource_data["resource"]),
                    recommendation_type=RecommendationType.LEARNING_RESOURCE,
                    confidence_score=resource_data["content_score"],
                    priority_score=resource_data["pattern_score"],
                    reasoning=f"Matches your knowledge gaps in {', '.join(resource_data['matched_concepts'])}",
                    target_concepts=resource_data["matched_concepts"],
                    prerequisites_met=True,  # Will be checked later
                    estimated_impact=resource_data["content_score"]
                )
                recommendations.append(rec)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in content-based filtering: {e}")
            return []
    
    async def _find_concept_matching_resources(self, gap_concepts: List[str]) -> List[Dict[str, Any]]:
        """Find resources that address the identified knowledge gaps"""
        # Mock resource database - in production, this would query actual resources
        mock_resources = [
            {
                "resource_id": "res_003",
                "title": "Advanced Python Loops",
                "description": "Master for loops, while loops, and list comprehensions",
                "resource_type": "interactive",
                "difficulty_level": "intermediate",
                "concepts": ["loops", "python_advanced", "list_comprehensions"],
                "prerequisites": ["python_basics", "functions"],
                "estimated_duration": 60,
                "url": "https://example.com/python-loops"
            },
            {
                "resource_id": "res_004",
                "title": "Object-Oriented Programming Basics",
                "description": "Introduction to classes and objects in Python",
                "resource_type": "course",
                "difficulty_level": "intermediate",
                "concepts": ["oop", "classes", "objects", "python_advanced"],
                "prerequisites": ["python_basics", "functions"],
                "estimated_duration": 120,
                "url": "https://example.com/oop-basics"
            },
            {
                "resource_id": "res_005",
                "title": "Algorithm Complexity Analysis",
                "description": "Understanding Big O notation and algorithm efficiency",
                "resource_type": "article",
                "difficulty_level": "advanced",
                "concepts": ["algorithms", "complexity", "big_o"],
                "prerequisites": ["data_structures", "algorithms_basics"],
                "estimated_duration": 90,
                "url": "https://example.com/complexity-analysis"
            }
        ]
        
        # Filter resources that match gap concepts
        matching_resources = []
        for resource in mock_resources:
            matched_concepts = list(set(resource["concepts"]) & set(gap_concepts))
            if matched_concepts:
                matching_resources.append({
                    "resource": resource,
                    "matched_concepts": matched_concepts,
                    "match_ratio": len(matched_concepts) / len(resource["concepts"])
                })
        
        return matching_resources
    
    def _score_resources_by_patterns(
        self, 
        resources: List[Dict[str, Any]], 
        learning_history: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Score resources based on student's learning patterns"""
        scored_resources = []
        
        # Analyze student's learning patterns
        avg_performance = self._calculate_average_performance(learning_history)
        preferred_difficulty = self._infer_preferred_difficulty(learning_history)
        
        for resource_data in resources:
            resource = resource_data["resource"]
            
            # Base score from concept matching
            content_score = resource_data["match_ratio"]
            
            # Adjust score based on difficulty preference
            difficulty_match = self._calculate_difficulty_match(
                resource["difficulty_level"], preferred_difficulty
            )
            
            # Adjust score based on estimated success probability
            success_probability = self._estimate_success_probability(
                resource, avg_performance
            )
            
            # Calculate final scores
            final_content_score = content_score * difficulty_match
            pattern_score = success_probability
            
            scored_resources.append({
                "resource": resource,
                "matched_concepts": resource_data["matched_concepts"],
                "content_score": final_content_score,
                "pattern_score": pattern_score
            })
        
        # Sort by content score
        scored_resources.sort(key=lambda x: x["content_score"], reverse=True)
        
        return scored_resources
    
    def _calculate_average_performance(self, learning_history: List[Dict[str, Any]]) -> float:
        """Calculate student's average performance"""
        if not learning_history:
            return 0.5  # Default to middle performance
        
        total_ratio = 0
        count = 0
        
        for perf in learning_history:
            score = perf.get("score", 0)
            max_score = perf.get("max_score", 1)
            if max_score > 0:
                total_ratio += score / max_score
                count += 1
        
        return total_ratio / count if count > 0 else 0.5
    
    def _infer_preferred_difficulty(self, learning_history: List[Dict[str, Any]]) -> DifficultyLevel:
        """Infer student's preferred difficulty level from history"""
        # Simplified inference - in production, this would be more sophisticated
        avg_performance = self._calculate_average_performance(learning_history)
        
        if avg_performance >= 0.8:
            return DifficultyLevel.ADVANCED
        elif avg_performance >= 0.6:
            return DifficultyLevel.INTERMEDIATE
        else:
            return DifficultyLevel.BEGINNER
    
    def _calculate_difficulty_match(
        self, 
        resource_difficulty: str, 
        preferred_difficulty: DifficultyLevel
    ) -> float:
        """Calculate how well resource difficulty matches student preference"""
        difficulty_order = {
            "beginner": 0,
            "intermediate": 1, 
            "advanced": 2,
            "expert": 3
        }
        
        resource_level = difficulty_order.get(resource_difficulty, 1)
        preferred_level = difficulty_order.get(preferred_difficulty.value, 1)
        
        # Perfect match gets 1.0, adjacent levels get 0.8, further levels get lower scores
        diff = abs(resource_level - preferred_level)
        
        if diff == 0:
            return 1.0
        elif diff == 1:
            return 0.8
        elif diff == 2:
            return 0.5
        else:
            return 0.2
    
    def _estimate_success_probability(
        self, 
        resource: Dict[str, Any], 
        avg_performance: float
    ) -> float:
        """Estimate probability of student success with this resource"""
        # Simplified estimation based on difficulty and student performance
        difficulty_factors = {
            "beginner": 0.9,
            "intermediate": 0.7,
            "advanced": 0.5,
            "expert": 0.3
        }
        
        difficulty_factor = difficulty_factors.get(resource["difficulty_level"], 0.7)
        
        # Combine student performance with resource difficulty
        success_prob = (avg_performance + difficulty_factor) / 2
        
        return max(0.1, min(0.9, success_prob))  # Clamp to reasonable range