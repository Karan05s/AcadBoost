"""
Recommendation Prioritization and Adaptation Service
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid

from app.models.recommendations import (
    Recommendation, RecommendationRequest, DifficultyLevel, 
    ResourceType, LearningStyle
)

logger = logging.getLogger(__name__)


class RecommendationPrioritizationService:
    """Service for prioritizing and adapting recommendations"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def prioritize_by_severity(
        self, 
        recommendations: List[Recommendation],
        gap_analysis: Dict[str, Any]
    ) -> List[Recommendation]:
        """
        Prioritize recommendations based on gap severity
        
        Requirements: 3.2 - Severity-based recommendation prioritization
        """
        try:
            logger.info(f"Prioritizing {len(recommendations)} recommendations by severity")
            
            # Get gap severity scores for each concept
            gap_severities = gap_analysis.get("gap_severities", {})
            
            # Calculate priority scores based on gap severity
            for rec in recommendations:
                severity_score = self._calculate_severity_score(rec, gap_severities)
                urgency_score = self._calculate_urgency_score(rec, gap_analysis)
                impact_score = self._calculate_impact_score(rec)
                
                # Combine scores with weights
                rec.priority_score = (
                    severity_score * 0.4 +      # 40% weight for severity
                    urgency_score * 0.3 +       # 30% weight for urgency
                    impact_score * 0.3          # 30% weight for impact
                )
            
            # Sort by priority score (highest first)
            recommendations.sort(key=lambda x: x.priority_score, reverse=True)
            
            logger.info("Recommendations prioritized by severity")
            return recommendations
            
        except Exception as e:
            logger.error(f"Error prioritizing recommendations by severity: {e}")
            return recommendations
    
    async def adapt_recommendations_by_progress(
        self, 
        student_id: str,
        recommendations: List[Recommendation]
    ) -> List[Recommendation]:
        """
        Adapt recommendations based on student progress
        
        Requirements: 3.4 - Adaptive recommendation updates based on progress
        """
        try:
            logger.info(f"Adapting recommendations for student {student_id}")
            
            # Get recent student performance
            recent_performance = await self._get_recent_performance(student_id)
            
            # Get completed recommendations
            completed_recs = await self._get_completed_recommendations(student_id)
            
            # Adapt recommendations based on progress
            adapted_recs = []
            
            for rec in recommendations:
                # Skip if already completed
                if rec.recommendation_id in completed_recs:
                    continue
                
                # Adjust based on recent performance in related concepts
                performance_adjustment = self._calculate_performance_adjustment(
                    rec, recent_performance
                )
                
                # Adjust based on learning velocity
                velocity_adjustment = self._calculate_velocity_adjustment(
                    rec, recent_performance
                )
                
                # Apply adjustments
                rec.confidence_score = min(1.0, rec.confidence_score * performance_adjustment)
                rec.priority_score = min(1.0, rec.priority_score * velocity_adjustment)
                
                # Update reasoning with adaptation info
                rec.reasoning += f" | Adapted based on recent progress (performance: {performance_adjustment:.2f}, velocity: {velocity_adjustment:.2f})"
                
                adapted_recs.append(rec)
            
            logger.info(f"Adapted {len(adapted_recs)} recommendations")
            return adapted_recs
            
        except Exception as e:
            logger.error(f"Error adapting recommendations: {e}")
            return recommendations
    
    async def apply_resource_diversity(
        self, 
        recommendations: List[Recommendation],
        diversity_factor: float = 0.3
    ) -> List[Recommendation]:
        """
        Apply resource type diversity to recommendations
        
        Requirements: 3.5 - Resource type diversity algorithms
        """
        try:
            logger.info(f"Applying resource diversity with factor {diversity_factor}")
            
            # Group recommendations by resource type
            type_groups = {}
            for rec in recommendations:
                resource_type = rec.resource.resource_type
                if resource_type not in type_groups:
                    type_groups[resource_type] = []
                type_groups[resource_type].append(rec)
            
            # Calculate diversity penalty for over-represented types
            total_recs = len(recommendations)
            ideal_per_type = total_recs / len(type_groups) if type_groups else 1
            
            diversified_recs = []
            
            for resource_type, type_recs in type_groups.items():
                # Calculate diversity penalty
                type_count = len(type_recs)
                if type_count > ideal_per_type:
                    penalty = 1.0 - (diversity_factor * (type_count - ideal_per_type) / ideal_per_type)
                    penalty = max(0.5, penalty)  # Minimum 50% of original score
                else:
                    penalty = 1.0
                
                # Apply penalty to recommendations of this type
                for rec in type_recs:
                    rec.confidence_score *= penalty
                    diversified_recs.append(rec)
            
            # Re-sort by adjusted confidence scores
            diversified_recs.sort(key=lambda x: x.confidence_score, reverse=True)
            
            logger.info("Resource diversity applied")
            return diversified_recs
            
        except Exception as e:
            logger.error(f"Error applying resource diversity: {e}")
            return recommendations
    
    async def apply_constraint_filters(
        self, 
        recommendations: List[Recommendation],
        constraints: Dict[str, Any]
    ) -> List[Recommendation]:
        """
        Apply constraint-aware recommendation filtering
        
        Requirements: 3.6 - Constraint-aware recommendation filtering
        """
        try:
            logger.info(f"Applying constraint filters: {list(constraints.keys())}")
            
            filtered_recs = []
            
            for rec in recommendations:
                # Check time constraints
                if "max_duration" in constraints:
                    max_duration = constraints["max_duration"]
                    if rec.resource.estimated_duration > max_duration:
                        continue
                
                # Check difficulty constraints
                if "difficulty_range" in constraints:
                    difficulty_range = constraints["difficulty_range"]
                    if rec.resource.difficulty_level not in difficulty_range:
                        continue
                
                # Check prerequisite constraints
                if "enforce_prerequisites" in constraints and constraints["enforce_prerequisites"]:
                    if not rec.prerequisites_met:
                        continue
                
                # Check resource type constraints
                if "allowed_resource_types" in constraints:
                    allowed_types = constraints["allowed_resource_types"]
                    if rec.resource.resource_type not in allowed_types:
                        continue
                
                # Check concept constraints
                if "required_concepts" in constraints:
                    required_concepts = constraints["required_concepts"]
                    if not any(concept in rec.target_concepts for concept in required_concepts):
                        continue
                
                # Check accessibility constraints
                if "accessibility_requirements" in constraints:
                    accessibility_reqs = constraints["accessibility_requirements"]
                    if not self._check_accessibility_compatibility(rec, accessibility_reqs):
                        continue
                
                filtered_recs.append(rec)
            
            logger.info(f"Filtered to {len(filtered_recs)} recommendations after applying constraints")
            return filtered_recs
            
        except Exception as e:
            logger.error(f"Error applying constraint filters: {e}")
            return recommendations
    
    def _calculate_severity_score(
        self, 
        rec: Recommendation, 
        gap_severities: Dict[str, float]
    ) -> float:
        """Calculate severity score for a recommendation"""
        # Get maximum severity for concepts addressed by this recommendation
        max_severity = 0.0
        
        for concept in rec.target_concepts:
            severity = gap_severities.get(concept, 0.5)  # Default to medium severity
            max_severity = max(max_severity, severity)
        
        return max_severity
    
    def _calculate_urgency_score(
        self, 
        rec: Recommendation, 
        gap_analysis: Dict[str, Any]
    ) -> float:
        """Calculate urgency score based on gap analysis"""
        # Factors that increase urgency:
        # - Concepts are prerequisites for other concepts
        # - Student is falling behind in related areas
        # - Upcoming assessments or deadlines
        
        urgency_factors = gap_analysis.get("urgency_factors", {})
        
        urgency_score = 0.5  # Base urgency
        
        for concept in rec.target_concepts:
            # Check if concept is a prerequisite for others
            if concept in urgency_factors.get("prerequisite_concepts", []):
                urgency_score += 0.2
            
            # Check if concept has upcoming assessments
            if concept in urgency_factors.get("upcoming_assessments", []):
                urgency_score += 0.3
        
        return min(1.0, urgency_score)
    
    def _calculate_impact_score(self, rec: Recommendation) -> float:
        """Calculate expected impact score"""
        # Base impact from recommendation
        base_impact = rec.estimated_impact
        
        # Adjust based on resource characteristics
        impact_multipliers = {
            ResourceType.INTERACTIVE: 1.2,
            ResourceType.PROJECT: 1.3,
            ResourceType.COURSE: 1.1,
            ResourceType.VIDEO: 1.0,
            ResourceType.ARTICLE: 0.9,
            ResourceType.QUIZ: 0.8
        }
        
        multiplier = impact_multipliers.get(rec.resource.resource_type, 1.0)
        
        return min(1.0, base_impact * multiplier)
    
    async def _get_recent_performance(self, student_id: str) -> List[Dict[str, Any]]:
        """Get recent student performance data"""
        try:
            # Get performance from last 30 days
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            cursor = self.db.student_performance.find({
                "student_id": student_id,
                "timestamp": {"$gte": cutoff_date}
            }).sort("timestamp", -1)
            
            performance_data = await cursor.to_list(length=50)  # Last 50 submissions
            return performance_data
            
        except Exception as e:
            logger.error(f"Error getting recent performance: {e}")
            return []
    
    async def _get_completed_recommendations(self, student_id: str) -> List[str]:
        """Get list of completed recommendation IDs"""
        try:
            cursor = self.db.recommendation_feedback.find({
                "student_id": student_id,
                "completed": True
            })
            
            feedback_data = await cursor.to_list(length=None)
            completed_ids = [feedback["recommendation_id"] for feedback in feedback_data]
            
            return completed_ids
            
        except Exception as e:
            logger.error(f"Error getting completed recommendations: {e}")
            return []
    
    def _calculate_performance_adjustment(
        self, 
        rec: Recommendation, 
        recent_performance: List[Dict[str, Any]]
    ) -> float:
        """Calculate performance-based adjustment factor"""
        if not recent_performance:
            return 1.0
        
        # Calculate average performance in related concepts
        related_performance = []
        
        for perf in recent_performance:
            # Check if performance involves concepts from this recommendation
            perf_concepts = []
            
            if "metadata" in perf and "concept_tags" in perf["metadata"]:
                perf_concepts.extend(perf["metadata"]["concept_tags"])
            
            if "question_responses" in perf:
                for response in perf["question_responses"]:
                    if "concept_tags" in response:
                        perf_concepts.extend(response["concept_tags"])
            
            # Check for overlap with recommendation concepts
            if any(concept in rec.target_concepts for concept in perf_concepts):
                score = perf.get("score", 0)
                max_score = perf.get("max_score", 1)
                performance_ratio = score / max_score if max_score > 0 else 0
                related_performance.append(performance_ratio)
        
        if not related_performance:
            return 1.0
        
        avg_performance = sum(related_performance) / len(related_performance)
        
        # Adjust confidence based on performance
        # Poor performance (< 0.5) increases confidence in recommendation
        # Good performance (> 0.8) decreases confidence (may not need it)
        if avg_performance < 0.5:
            return 1.2  # Boost confidence
        elif avg_performance > 0.8:
            return 0.8  # Reduce confidence
        else:
            return 1.0  # No adjustment
    
    def _calculate_velocity_adjustment(
        self, 
        rec: Recommendation, 
        recent_performance: List[Dict[str, Any]]
    ) -> float:
        """Calculate learning velocity-based adjustment"""
        if len(recent_performance) < 2:
            return 1.0
        
        # Calculate learning velocity (improvement over time)
        performance_scores = []
        
        for perf in recent_performance:
            score = perf.get("score", 0)
            max_score = perf.get("max_score", 1)
            performance_ratio = score / max_score if max_score > 0 else 0
            timestamp = perf.get("timestamp", datetime.utcnow())
            
            performance_scores.append((timestamp, performance_ratio))
        
        # Sort by timestamp
        performance_scores.sort(key=lambda x: x[0])
        
        # Calculate trend (simple linear regression slope)
        if len(performance_scores) >= 3:
            # Calculate slope of performance over time
            x_values = [(score[0] - performance_scores[0][0]).total_seconds() for score in performance_scores]
            y_values = [score[1] for score in performance_scores]
            
            n = len(x_values)
            sum_x = sum(x_values)
            sum_y = sum(y_values)
            sum_xy = sum(x * y for x, y in zip(x_values, y_values))
            sum_x2 = sum(x * x for x in x_values)
            
            if n * sum_x2 - sum_x * sum_x != 0:
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                
                # Adjust priority based on learning velocity
                if slope > 0:
                    return 1.1  # Positive trend, slightly boost priority
                elif slope < -0.1:
                    return 1.3  # Negative trend, significantly boost priority
        
        return 1.0  # No adjustment
    
    def _check_accessibility_compatibility(
        self, 
        rec: Recommendation, 
        accessibility_reqs: List[str]
    ) -> bool:
        """Check if recommendation meets accessibility requirements"""
        # Mock accessibility check - in production, this would check actual resource metadata
        resource_accessibility = rec.resource.metadata.get("accessibility_features", [])
        
        # Check if all required accessibility features are supported
        for req in accessibility_reqs:
            if req not in resource_accessibility:
                # For mock purposes, assume basic accessibility support
                if req in ["screen_reader", "keyboard_navigation", "high_contrast"]:
                    continue
                else:
                    return False
        
        return True