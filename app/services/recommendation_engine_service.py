"""
Recommendation Engine Service for personalized learning recommendations
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid
import math

from app.models.recommendations import (
    RecommendationRequest, RecommendationResponse, Recommendation,
    LearningResource, LearningPath, RecommendationType, LearningStyle,
    DifficultyLevel, ResourceType, StudentPreferences, RecommendationMetrics
)
from app.services.collaborative_filtering import CollaborativeFilteringAlgorithm
from app.services.content_based_filtering import ContentBasedFilteringAlgorithm
from app.services.recommendation_prioritization_service import RecommendationPrioritizationService

logger = logging.getLogger(__name__)


class LearningPathGenerator:
    """Generates structured learning paths with prerequisite ordering"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def generate_path(
        self, 
        student_id: str, 
        target_concepts: List[str],
        max_duration: Optional[int] = None
    ) -> LearningPath:
        """Generate a learning path with proper prerequisite ordering"""
        try:
            # Build concept dependency graph
            concept_graph = await self._build_concept_graph(target_concepts)
            
            # Order concepts by prerequisites (topological sort)
            ordered_concepts = self._topological_sort(concept_graph)
            
            # Generate recommendations for each concept in order
            path_recommendations = []
            total_duration = 0
            
            for concept in ordered_concepts:
                if max_duration and total_duration >= max_duration:
                    break
                
                # Get best resource for this concept
                concept_resources = await self._get_concept_resources(concept)
                
                if concept_resources:
                    best_resource = concept_resources[0]  # Take the best one
                    
                    rec = Recommendation(
                        recommendation_id=str(uuid.uuid4()),
                        student_id=student_id,
                        resource=LearningResource(**best_resource),
                        recommendation_type=RecommendationType.LEARNING_RESOURCE,
                        confidence_score=0.8,
                        priority_score=0.9,
                        reasoning=f"Essential for mastering {concept}",
                        target_concepts=[concept],
                        prerequisites_met=True,
                        estimated_impact=0.8
                    )
                    
                    path_recommendations.append(rec)
                    total_duration += best_resource["estimated_duration"]
            
            # Create learning path
            path = LearningPath(
                path_id=str(uuid.uuid4()),
                student_id=student_id,
                title=f"Learning Path: {', '.join(target_concepts)}",
                description=f"Structured path to master {len(target_concepts)} concepts",
                target_concepts=target_concepts,
                recommendations=path_recommendations,
                estimated_duration=total_duration,
                difficulty_progression=[rec.resource.difficulty_level for rec in path_recommendations]
            )
            
            return path
            
        except Exception as e:
            logger.error(f"Error generating learning path: {e}")
            raise
    
    async def _build_concept_graph(self, concepts: List[str]) -> Dict[str, List[str]]:
        """Build a dependency graph for concepts"""
        # Mock concept dependencies - in production, this would come from a knowledge base
        concept_dependencies = {
            "python_basics": [],
            "functions": ["python_basics"],
            "loops": ["python_basics"],
            "data_structures": ["python_basics", "functions"],
            "oop": ["functions", "data_structures"],
            "algorithms": ["data_structures", "loops"],
            "complexity": ["algorithms"],
            "python_advanced": ["oop", "algorithms"]
        }
        
        # Build subgraph for requested concepts
        graph = {}
        for concept in concepts:
            if concept in concept_dependencies:
                graph[concept] = concept_dependencies[concept]
            else:
                graph[concept] = []  # No known dependencies
        
        return graph
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        """Perform topological sort to order concepts by prerequisites"""
        # Simple topological sort implementation
        visited = set()
        temp_visited = set()
        result = []
        
        def visit(node):
            if node in temp_visited:
                # Cycle detected - handle gracefully
                return
            if node in visited:
                return
            
            temp_visited.add(node)
            
            # Visit dependencies first
            for dependency in graph.get(node, []):
                if dependency in graph:  # Only visit if it's in our target concepts
                    visit(dependency)
            
            temp_visited.remove(node)
            visited.add(node)
            result.append(node)
        
        # Visit all nodes
        for concept in graph:
            if concept not in visited:
                visit(concept)
        
        return result
    
    async def _get_concept_resources(self, concept: str) -> List[Dict[str, Any]]:
        """Get resources for a specific concept"""
        # Mock resources for concepts
        concept_resources = {
            "python_basics": [{
                "resource_id": "res_python_basics",
                "title": "Python Fundamentals",
                "description": "Learn Python basics: variables, data types, operators",
                "resource_type": "course",
                "difficulty_level": "beginner",
                "concepts": ["python_basics"],
                "prerequisites": [],
                "estimated_duration": 120,
                "url": "https://example.com/python-basics"
            }],
            "functions": [{
                "resource_id": "res_functions",
                "title": "Python Functions Mastery",
                "description": "Master function definition, parameters, and return values",
                "resource_type": "tutorial",
                "difficulty_level": "beginner",
                "concepts": ["functions"],
                "prerequisites": ["python_basics"],
                "estimated_duration": 90,
                "url": "https://example.com/functions"
            }],
            "loops": [{
                "resource_id": "res_loops",
                "title": "Loops and Iteration",
                "description": "Master for loops, while loops, and iteration patterns",
                "resource_type": "interactive",
                "difficulty_level": "intermediate",
                "concepts": ["loops"],
                "prerequisites": ["python_basics"],
                "estimated_duration": 75,
                "url": "https://example.com/loops"
            }]
        }
        
        return concept_resources.get(concept, [])


class RecommendationEngineService:
    """Service for generating personalized learning recommendations"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        # Initialize recommendation algorithms
        self.collaborative_filter = CollaborativeFilteringAlgorithm(db)
        self.content_based_filter = ContentBasedFilteringAlgorithm(db)
        self.learning_path_generator = LearningPathGenerator(db)
        self.prioritization_service = RecommendationPrioritizationService(db)
    
    async def generate_personalized_recommendations(
        self, 
        request: RecommendationRequest
    ) -> RecommendationResponse:
        """
        Generate personalized recommendations for a student
        
        Requirements: 3.1, 3.3 - Personalized recommendations based on gaps and preferences
        """
        try:
            logger.info(f"Generating recommendations for student {request.student_id}")
            
            # Get student preferences and learning history
            student_prefs = await self._get_student_preferences(request.student_id)
            learning_history = await self._get_learning_history(request.student_id)
            
            # Merge request preferences with stored preferences
            merged_request = self._merge_preferences(request, student_prefs)
            
            # Generate recommendations using multiple algorithms
            collaborative_recs = await self.collaborative_filter.generate_recommendations(
                merged_request, learning_history
            )
            
            content_based_recs = await self.content_based_filter.generate_recommendations(
                merged_request, learning_history
            )
            
            # Combine and rank recommendations
            combined_recs = self._combine_recommendations(
                collaborative_recs, content_based_recs, merged_request
            )
            
            # Apply personalization filters
            personalized_recs = await self._apply_personalization_filters(
                combined_recs, merged_request, student_prefs
            )
            
            # Limit to reasonable number of recommendations
            final_recs = personalized_recs[:20]  # Top 20 recommendations
            
            # Store recommendations for tracking
            await self._store_recommendations(final_recs)
            
            logger.info(f"Generated {len(final_recs)} recommendations for student {request.student_id}")
            
            return RecommendationResponse(
                student_id=request.student_id,
                recommendations=final_recs,
                total_count=len(final_recs),
                metadata={
                    "algorithms_used": ["collaborative_filtering", "content_based"],
                    "personalization_applied": True,
                    "gap_concepts_addressed": request.gap_concepts
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating recommendations for student {request.student_id}: {e}")
            raise
    async def generate_learning_path(
        self, 
        student_id: str, 
        target_concepts: List[str],
        max_duration: Optional[int] = None
    ) -> LearningPath:
        """
        Generate a structured learning path with prerequisite ordering
        
        Requirements: 3.1 - Learning path generation with prerequisite ordering
        """
        try:
            logger.info(f"Generating learning path for student {student_id}, concepts: {target_concepts}")
            
            # Generate learning path using specialized algorithm
            learning_path = await self.learning_path_generator.generate_path(
                student_id, target_concepts, max_duration
            )
            
            # Store learning path
            await self.db.learning_paths.insert_one(learning_path.dict())
            
            logger.info(f"Generated learning path {learning_path.path_id} for student {student_id}")
            
            return learning_path
            
        except Exception as e:
            logger.error(f"Error generating learning path for student {student_id}: {e}")
            raise
    
    async def update_recommendation_feedback(
        self, 
        recommendation_id: str, 
        feedback_data: Dict[str, Any]
    ) -> bool:
        """
        Update recommendation effectiveness based on student feedback
        
        Requirements: 5.4 - Recommendation effectiveness tracking
        """
        try:
            # Store feedback
            feedback_record = {
                "feedback_id": str(uuid.uuid4()),
                "recommendation_id": recommendation_id,
                "student_id": feedback_data.get("student_id"),
                "completed": feedback_data.get("completed", False),
                "effectiveness_rating": feedback_data.get("effectiveness_rating"),
                "difficulty_rating": feedback_data.get("difficulty_rating"),
                "time_spent": feedback_data.get("time_spent"),
                "helpful": feedback_data.get("helpful"),
                "comments": feedback_data.get("comments"),
                "created_at": datetime.utcnow()
            }
            
            await self.db.recommendation_feedback.insert_one(feedback_record)
            
            # Update recommendation metrics
            await self._update_recommendation_metrics(recommendation_id, feedback_data)
            
            logger.info(f"Updated feedback for recommendation {recommendation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating recommendation feedback: {e}")
            return False
    
    async def _get_student_preferences(self, student_id: str) -> Optional[StudentPreferences]:
        """Get student learning preferences"""
        try:
            prefs_data = await self.db.student_preferences.find_one({"student_id": student_id})
            if prefs_data:
                return StudentPreferences(**prefs_data)
            return None
        except Exception as e:
            logger.error(f"Error getting student preferences: {e}")
            return None
    
    async def _get_learning_history(self, student_id: str) -> List[Dict[str, Any]]:
        """Get student's learning history"""
        try:
            cursor = self.db.student_performance.find({"student_id": student_id}).sort("timestamp", -1)
            history = await cursor.to_list(length=100)  # Last 100 submissions
            return history
        except Exception as e:
            logger.error(f"Error getting learning history: {e}")
            return []
    
    def _merge_preferences(
        self, 
        request: RecommendationRequest, 
        stored_prefs: Optional[StudentPreferences]
    ) -> RecommendationRequest:
        """Merge request preferences with stored student preferences"""
        if not stored_prefs:
            return request
        
        # Use request preferences if provided, otherwise fall back to stored preferences
        merged_data = request.dict()
        
        if not merged_data.get("learning_style") and stored_prefs.learning_style:
            merged_data["learning_style"] = stored_prefs.learning_style
        
        if not merged_data.get("difficulty_preference") and stored_prefs.difficulty_preference:
            merged_data["difficulty_preference"] = stored_prefs.difficulty_preference
        
        if not merged_data.get("resource_types") and stored_prefs.preferred_resource_types:
            merged_data["resource_types"] = stored_prefs.preferred_resource_types
        
        if not merged_data.get("time_available") and stored_prefs.study_time_preference:
            merged_data["time_available"] = stored_prefs.study_time_preference
        
        return RecommendationRequest(**merged_data)
    
    def _combine_recommendations(
        self, 
        collaborative_recs: List[Recommendation],
        content_based_recs: List[Recommendation],
        request: RecommendationRequest
    ) -> List[Recommendation]:
        """Combine recommendations from different algorithms"""
        # Create a map to avoid duplicates
        rec_map = {}
        
        # Add collaborative filtering recommendations with higher weight
        for rec in collaborative_recs:
            rec.confidence_score *= 0.7  # Weight for collaborative filtering
            rec_map[rec.resource.resource_id] = rec
        
        # Add content-based recommendations
        for rec in content_based_recs:
            resource_id = rec.resource.resource_id
            if resource_id in rec_map:
                # Combine scores if resource already exists
                existing_rec = rec_map[resource_id]
                combined_score = (existing_rec.confidence_score + rec.confidence_score * 0.5) / 1.5
                existing_rec.confidence_score = min(combined_score, 1.0)
                existing_rec.reasoning += f" | {rec.reasoning}"
            else:
                rec.confidence_score *= 0.5  # Weight for content-based
                rec_map[resource_id] = rec
        
        # Sort by combined confidence score
        combined_recs = list(rec_map.values())
        combined_recs.sort(key=lambda x: x.confidence_score, reverse=True)
        
        return combined_recs
    
    async def _apply_personalization_filters(
        self, 
        recommendations: List[Recommendation],
        request: RecommendationRequest,
        student_prefs: Optional[StudentPreferences]
    ) -> List[Recommendation]:
        """Apply personalization filters to recommendations"""
        filtered_recs = []
        
        for rec in recommendations:
            # Filter by time availability
            if request.time_available and rec.resource.estimated_duration > request.time_available:
                continue
            
            # Filter by resource type preferences
            if request.resource_types and rec.resource.resource_type not in request.resource_types:
                continue
            
            # Filter by difficulty preference
            if request.difficulty_preference and rec.resource.difficulty_level != request.difficulty_preference:
                # Allow one level up or down
                difficulty_order = [DifficultyLevel.BEGINNER, DifficultyLevel.INTERMEDIATE, 
                                 DifficultyLevel.ADVANCED, DifficultyLevel.EXPERT]
                pref_idx = difficulty_order.index(request.difficulty_preference)
                rec_idx = difficulty_order.index(rec.resource.difficulty_level)
                if abs(pref_idx - rec_idx) > 1:
                    continue
            
            # Boost score based on learning style match
            if request.learning_style:
                rec.confidence_score = self._apply_learning_style_boost(rec, request.learning_style)
            
            # Check if prerequisites are met
            rec.prerequisites_met = await self._check_prerequisites(
                request.student_id, rec.resource.prerequisites
            )
            
            # Lower priority if prerequisites not met
            if not rec.prerequisites_met:
                rec.priority_score *= 0.5
            
            filtered_recs.append(rec)
        
        # Sort by priority and confidence
        filtered_recs.sort(key=lambda x: (x.priority_score, x.confidence_score), reverse=True)
        
        return filtered_recs
    
    def _apply_learning_style_boost(self, rec: Recommendation, learning_style: LearningStyle) -> float:
        """Apply learning style boost to recommendation score"""
        base_score = rec.confidence_score
        
        # Define resource type preferences for each learning style
        style_preferences = {
            LearningStyle.VISUAL: [ResourceType.VIDEO, ResourceType.INTERACTIVE],
            LearningStyle.AUDITORY: [ResourceType.VIDEO, ResourceType.COURSE],
            LearningStyle.KINESTHETIC: [ResourceType.INTERACTIVE, ResourceType.PROJECT],
            LearningStyle.READING_WRITING: [ResourceType.ARTICLE, ResourceType.BOOK, ResourceType.TUTORIAL]
        }
        
        preferred_types = style_preferences.get(learning_style, [])
        
        if rec.resource.resource_type in preferred_types:
            # Boost score by 20% for matching learning style
            return min(base_score * 1.2, 1.0)
        
        return base_score
    
    async def _check_prerequisites(self, student_id: str, prerequisites: List[str]) -> bool:
        """Check if student has met prerequisites"""
        if not prerequisites:
            return True
        
        try:
            # Check if student has demonstrated competency in prerequisite concepts
            for concept in prerequisites:
                # Look for successful submissions involving this concept
                performance = await self.db.student_performance.find_one({
                    "student_id": student_id,
                    "$or": [
                        {"metadata.concept_tags": concept},
                        {"question_responses.concept_tags": concept}
                    ],
                    "score": {"$gte": 0.7}  # 70% threshold for competency
                })
                
                if not performance:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking prerequisites: {e}")
            return False
    
    async def _store_recommendations(self, recommendations: List[Recommendation]) -> None:
        """Store recommendations for tracking and analytics"""
        try:
            rec_docs = [rec.dict() for rec in recommendations]
            if rec_docs:
                await self.db.recommendations.insert_many(rec_docs)
        except Exception as e:
            logger.error(f"Error storing recommendations: {e}")
    
    async def _update_recommendation_metrics(
        self, 
        recommendation_id: str, 
        feedback_data: Dict[str, Any]
    ) -> None:
        """Update recommendation performance metrics"""
        try:
            # Get existing metrics or create new
            metrics = await self.db.recommendation_metrics.find_one(
                {"recommendation_id": recommendation_id}
            )
            
            if not metrics:
                metrics = {
                    "recommendation_id": recommendation_id,
                    "student_id": feedback_data.get("student_id"),
                    "click_through_rate": 0.0,
                    "completion_rate": 0.0,
                    "average_rating": None,
                    "total_interactions": 0,
                    "successful_completions": 0,
                    "average_time_to_complete": None
                }
            
            # Update metrics based on feedback
            metrics["total_interactions"] += 1
            
            if feedback_data.get("completed"):
                metrics["successful_completions"] += 1
            
            # Recalculate completion rate
            metrics["completion_rate"] = metrics["successful_completions"] / metrics["total_interactions"]
            
            # Update average rating if provided
            if feedback_data.get("effectiveness_rating"):
                current_avg = metrics.get("average_rating", 0) or 0
                total_interactions = metrics["total_interactions"]
                new_rating = feedback_data["effectiveness_rating"]
                
                if current_avg == 0:
                    metrics["average_rating"] = new_rating
                else:
                    # Calculate running average
                    metrics["average_rating"] = (
                        (current_avg * (total_interactions - 1) + new_rating) / total_interactions
                    )
            
            metrics["last_updated"] = datetime.utcnow()
            
            # Upsert metrics
            await self.db.recommendation_metrics.update_one(
                {"recommendation_id": recommendation_id},
                {"$set": metrics},
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"Error updating recommendation metrics: {e}")
    
    async def prioritize_recommendations_by_severity(
        self, 
        recommendations: List[Recommendation],
        gap_analysis: Dict[str, Any]
    ) -> List[Recommendation]:
        """
        Prioritize recommendations based on gap severity
        
        Requirements: 3.2 - Severity-based recommendation prioritization
        """
        return await self.prioritization_service.prioritize_by_severity(
            recommendations, gap_analysis
        )
    
    async def adapt_recommendations_by_progress(
        self, 
        student_id: str,
        recommendations: List[Recommendation]
    ) -> List[Recommendation]:
        """
        Adapt recommendations based on student progress
        
        Requirements: 3.4 - Adaptive recommendation updates based on progress
        """
        return await self.prioritization_service.adapt_recommendations_by_progress(
            student_id, recommendations
        )
    
    async def apply_resource_diversity(
        self, 
        recommendations: List[Recommendation],
        diversity_factor: float = 0.3
    ) -> List[Recommendation]:
        """
        Apply resource type diversity to recommendations
        
        Requirements: 3.5 - Resource type diversity algorithms
        """
        return await self.prioritization_service.apply_resource_diversity(
            recommendations, diversity_factor
        )
    
    async def apply_constraint_filters(
        self, 
        recommendations: List[Recommendation],
        constraints: Dict[str, Any]
    ) -> List[Recommendation]:
        """
        Apply constraint-aware recommendation filtering
        
        Requirements: 3.6 - Constraint-aware recommendation filtering
        """
        return await self.prioritization_service.apply_constraint_filters(
            recommendations, constraints
        )