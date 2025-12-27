"""
Recommendation Effectiveness Tracking Service
"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid

from app.models.recommendations import (
    RecommendationMetrics, RecommendationFeedback
)

logger = logging.getLogger(__name__)


class RecommendationEffectivenessService:
    """Service for tracking and analyzing recommendation effectiveness"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def track_recommendation_completion(
        self, 
        recommendation_id: str,
        student_id: str,
        completion_data: Dict[str, Any]
    ) -> bool:
        """
        Track recommendation completion
        
        Requirements: 5.4 - Recommendation completion tracking
        """
        try:
            logger.info(f"Tracking completion for recommendation {recommendation_id}")
            
            # Create completion record
            completion_record = {
                "completion_id": str(uuid.uuid4()),
                "recommendation_id": recommendation_id,
                "student_id": student_id,
                "completed_at": datetime.utcnow(),
                "time_spent": completion_data.get("time_spent"),
                "completion_percentage": completion_data.get("completion_percentage", 100),
                "success_indicators": completion_data.get("success_indicators", {}),
                "metadata": completion_data.get("metadata", {})
            }
            
            # Store completion record
            await self.db.recommendation_completions.insert_one(completion_record)
            
            # Update recommendation metrics
            await self._update_completion_metrics(recommendation_id, completion_data)
            
            logger.info(f"Completion tracked for recommendation {recommendation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error tracking recommendation completion: {e}")
            return False
    
    async def collect_effectiveness_rating(
        self, 
        recommendation_id: str,
        student_id: str,
        rating_data: Dict[str, Any]
    ) -> bool:
        """
        Collect effectiveness rating from student
        
        Requirements: 5.4 - Effectiveness rating collection
        """
        try:
            logger.info(f"Collecting effectiveness rating for recommendation {recommendation_id}")
            
            # Create rating record
            rating_record = {
                "rating_id": str(uuid.uuid4()),
                "recommendation_id": recommendation_id,
                "student_id": student_id,
                "effectiveness_rating": rating_data.get("effectiveness_rating"),
                "difficulty_rating": rating_data.get("difficulty_rating"),
                "relevance_rating": rating_data.get("relevance_rating"),
                "engagement_rating": rating_data.get("engagement_rating"),
                "would_recommend": rating_data.get("would_recommend"),
                "comments": rating_data.get("comments"),
                "rating_timestamp": datetime.utcnow(),
                "context": rating_data.get("context", {})
            }
            
            # Store rating record
            await self.db.recommendation_ratings.insert_one(rating_record)
            
            # Update recommendation metrics
            await self._update_rating_metrics(recommendation_id, rating_data)
            
            logger.info(f"Effectiveness rating collected for recommendation {recommendation_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error collecting effectiveness rating: {e}")
            return False
    
    async def analyze_recommendation_performance(
        self, 
        recommendation_id: Optional[str] = None,
        student_id: Optional[str] = None,
        time_period: Optional[int] = 30
    ) -> Dict[str, Any]:
        """
        Analyze recommendation performance analytics
        
        Requirements: 5.4 - Recommendation performance analytics
        """
        try:
            logger.info(f"Analyzing recommendation performance (rec_id: {recommendation_id}, student: {student_id})")
            
            # Build query filters
            filters = {}
            if recommendation_id:
                filters["recommendation_id"] = recommendation_id
            if student_id:
                filters["student_id"] = student_id
            if time_period:
                cutoff_date = datetime.utcnow() - timedelta(days=time_period)
                filters["created_at"] = {"$gte": cutoff_date}
            
            # Get completion data
            completion_stats = await self._analyze_completion_stats(filters)
            
            # Get rating data
            rating_stats = await self._analyze_rating_stats(filters)
            
            # Get engagement data
            engagement_stats = await self._analyze_engagement_stats(filters)
            
            # Calculate overall performance metrics
            performance_analysis = {
                "completion_stats": completion_stats,
                "rating_stats": rating_stats,
                "engagement_stats": engagement_stats,
                "overall_effectiveness": self._calculate_overall_effectiveness(
                    completion_stats, rating_stats, engagement_stats
                ),
                "recommendations_for_improvement": self._generate_improvement_recommendations(
                    completion_stats, rating_stats, engagement_stats
                ),
                "analysis_timestamp": datetime.utcnow(),
                "filters_applied": filters
            }
            
            logger.info("Recommendation performance analysis completed")
            return performance_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing recommendation performance: {e}")
            return {}
    
    async def suggest_alternative_strategies(
        self, 
        student_id: str,
        failed_recommendations: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Suggest alternative strategies for failed recommendations
        
        Requirements: 5.4 - Alternative strategy suggestion logic
        """
        try:
            logger.info(f"Suggesting alternative strategies for student {student_id}")
            
            # Analyze failure patterns
            failure_patterns = await self._analyze_failure_patterns(student_id, failed_recommendations)
            
            # Generate alternative strategies
            alternative_strategies = []
            
            # Strategy 1: Adjust difficulty level
            if failure_patterns.get("difficulty_too_high", False):
                alternative_strategies.append({
                    "strategy_type": "difficulty_adjustment",
                    "description": "Recommend easier resources to build confidence",
                    "adjustments": {
                        "difficulty_level": "beginner",
                        "prerequisite_enforcement": True
                    },
                    "confidence": 0.8
                })
            
            # Strategy 2: Change resource type
            if failure_patterns.get("resource_type_mismatch", False):
                preferred_types = failure_patterns.get("preferred_resource_types", [])
                alternative_strategies.append({
                    "strategy_type": "resource_type_change",
                    "description": f"Focus on {', '.join(preferred_types)} resources",
                    "adjustments": {
                        "preferred_resource_types": preferred_types,
                        "avoid_resource_types": failure_patterns.get("avoided_types", [])
                    },
                    "confidence": 0.7
                })
            
            # Strategy 3: Adjust learning style
            if failure_patterns.get("learning_style_mismatch", False):
                alternative_strategies.append({
                    "strategy_type": "learning_style_adjustment",
                    "description": "Adapt to different learning style preferences",
                    "adjustments": {
                        "learning_style": failure_patterns.get("inferred_learning_style"),
                        "multimodal_approach": True
                    },
                    "confidence": 0.6
                })
            
            # Strategy 4: Break down into smaller chunks
            if failure_patterns.get("duration_too_long", False):
                alternative_strategies.append({
                    "strategy_type": "micro_learning",
                    "description": "Break learning into smaller, manageable chunks",
                    "adjustments": {
                        "max_duration": 15,  # 15-minute chunks
                        "sequential_delivery": True
                    },
                    "confidence": 0.9
                })
            
            # Strategy 5: Add gamification elements
            if failure_patterns.get("low_engagement", False):
                alternative_strategies.append({
                    "strategy_type": "gamification",
                    "description": "Add interactive and gamified elements",
                    "adjustments": {
                        "prefer_interactive": True,
                        "include_assessments": True,
                        "progress_tracking": True
                    },
                    "confidence": 0.7
                })
            
            logger.info(f"Generated {len(alternative_strategies)} alternative strategies")
            return alternative_strategies
            
        except Exception as e:
            logger.error(f"Error suggesting alternative strategies: {e}")
            return []
    
    async def _update_completion_metrics(
        self, 
        recommendation_id: str, 
        completion_data: Dict[str, Any]
    ) -> None:
        """Update completion-related metrics"""
        try:
            # Get existing metrics
            metrics = await self.db.recommendation_metrics.find_one(
                {"recommendation_id": recommendation_id}
            )
            
            if not metrics:
                metrics = {
                    "recommendation_id": recommendation_id,
                    "total_views": 0,
                    "total_completions": 0,
                    "completion_rate": 0.0,
                    "average_completion_time": 0.0,
                    "success_rate": 0.0
                }
            
            # Update completion metrics
            metrics["total_completions"] += 1
            
            # Update completion rate (assuming we track views separately)
            if metrics["total_views"] > 0:
                metrics["completion_rate"] = metrics["total_completions"] / metrics["total_views"]
            
            # Update average completion time
            time_spent = completion_data.get("time_spent", 0)
            if time_spent > 0:
                current_avg = metrics.get("average_completion_time", 0)
                total_completions = metrics["total_completions"]
                
                if current_avg == 0:
                    metrics["average_completion_time"] = time_spent
                else:
                    metrics["average_completion_time"] = (
                        (current_avg * (total_completions - 1) + time_spent) / total_completions
                    )
            
            # Update success rate based on completion percentage
            completion_percentage = completion_data.get("completion_percentage", 100)
            if completion_percentage >= 80:  # Consider 80%+ as successful
                metrics["successful_completions"] = metrics.get("successful_completions", 0) + 1
                metrics["success_rate"] = metrics["successful_completions"] / metrics["total_completions"]
            
            metrics["last_updated"] = datetime.utcnow()
            
            # Upsert metrics
            await self.db.recommendation_metrics.update_one(
                {"recommendation_id": recommendation_id},
                {"$set": metrics},
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"Error updating completion metrics: {e}")
    
    async def _update_rating_metrics(
        self, 
        recommendation_id: str, 
        rating_data: Dict[str, Any]
    ) -> None:
        """Update rating-related metrics"""
        try:
            # Get existing metrics
            metrics = await self.db.recommendation_metrics.find_one(
                {"recommendation_id": recommendation_id}
            )
            
            if not metrics:
                return
            
            # Update rating metrics
            effectiveness_rating = rating_data.get("effectiveness_rating")
            if effectiveness_rating:
                current_avg = metrics.get("average_effectiveness_rating", 0) or 0
                total_ratings = metrics.get("total_ratings", 0) + 1
                
                if current_avg == 0:
                    metrics["average_effectiveness_rating"] = effectiveness_rating
                else:
                    metrics["average_effectiveness_rating"] = (
                        (current_avg * (total_ratings - 1) + effectiveness_rating) / total_ratings
                    )
                
                metrics["total_ratings"] = total_ratings
            
            # Update recommendation likelihood
            would_recommend = rating_data.get("would_recommend")
            if would_recommend is not None:
                total_recommendations = metrics.get("total_recommendation_responses", 0) + 1
                positive_recommendations = metrics.get("positive_recommendations", 0)
                
                if would_recommend:
                    positive_recommendations += 1
                
                metrics["positive_recommendations"] = positive_recommendations
                metrics["total_recommendation_responses"] = total_recommendations
                metrics["recommendation_likelihood"] = positive_recommendations / total_recommendations
            
            metrics["last_updated"] = datetime.utcnow()
            
            # Update metrics
            await self.db.recommendation_metrics.update_one(
                {"recommendation_id": recommendation_id},
                {"$set": metrics}
            )
            
        except Exception as e:
            logger.error(f"Error updating rating metrics: {e}")
    
    async def _analyze_completion_stats(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze completion statistics"""
        try:
            # Get completion data
            cursor = self.db.recommendation_completions.find(filters)
            completions = await cursor.to_list(length=None)
            
            if not completions:
                return {"total_completions": 0, "average_completion_time": 0}
            
            total_completions = len(completions)
            completion_times = [c.get("time_spent", 0) for c in completions if c.get("time_spent")]
            avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else 0
            
            # Calculate completion rate by day
            completion_by_day = {}
            for completion in completions:
                day = completion["completed_at"].date()
                completion_by_day[day] = completion_by_day.get(day, 0) + 1
            
            return {
                "total_completions": total_completions,
                "average_completion_time": avg_completion_time,
                "completion_by_day": completion_by_day,
                "completion_time_distribution": {
                    "min": min(completion_times) if completion_times else 0,
                    "max": max(completion_times) if completion_times else 0,
                    "median": sorted(completion_times)[len(completion_times)//2] if completion_times else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing completion stats: {e}")
            return {}
    
    async def _analyze_rating_stats(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze rating statistics"""
        try:
            # Get rating data
            cursor = self.db.recommendation_ratings.find(filters)
            ratings = await cursor.to_list(length=None)
            
            if not ratings:
                return {"total_ratings": 0}
            
            effectiveness_ratings = [r.get("effectiveness_rating") for r in ratings if r.get("effectiveness_rating")]
            difficulty_ratings = [r.get("difficulty_rating") for r in ratings if r.get("difficulty_rating")]
            
            return {
                "total_ratings": len(ratings),
                "average_effectiveness": sum(effectiveness_ratings) / len(effectiveness_ratings) if effectiveness_ratings else 0,
                "average_difficulty": sum(difficulty_ratings) / len(difficulty_ratings) if difficulty_ratings else 0,
                "rating_distribution": {
                    "effectiveness": self._calculate_rating_distribution(effectiveness_ratings),
                    "difficulty": self._calculate_rating_distribution(difficulty_ratings)
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing rating stats: {e}")
            return {}
    
    async def _analyze_engagement_stats(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze engagement statistics"""
        try:
            # This would analyze click-through rates, time spent, etc.
            # For now, return mock engagement data
            return {
                "click_through_rate": 0.75,
                "average_session_duration": 25.5,
                "bounce_rate": 0.15,
                "return_rate": 0.60
            }
            
        except Exception as e:
            logger.error(f"Error analyzing engagement stats: {e}")
            return {}
    
    def _calculate_overall_effectiveness(
        self, 
        completion_stats: Dict[str, Any],
        rating_stats: Dict[str, Any],
        engagement_stats: Dict[str, Any]
    ) -> float:
        """Calculate overall effectiveness score"""
        try:
            # Weighted combination of different metrics
            completion_score = min(1.0, completion_stats.get("total_completions", 0) / 10)  # Normalize to 0-1
            rating_score = rating_stats.get("average_effectiveness", 0) / 5  # Convert 1-5 scale to 0-1
            engagement_score = engagement_stats.get("click_through_rate", 0)
            
            # Weighted average
            overall_score = (
                completion_score * 0.4 +
                rating_score * 0.4 +
                engagement_score * 0.2
            )
            
            return round(overall_score, 3)
            
        except Exception as e:
            logger.error(f"Error calculating overall effectiveness: {e}")
            return 0.0
    
    def _generate_improvement_recommendations(
        self, 
        completion_stats: Dict[str, Any],
        rating_stats: Dict[str, Any],
        engagement_stats: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations for improvement"""
        recommendations = []
        
        # Check completion rates
        if completion_stats.get("total_completions", 0) < 5:
            recommendations.append("Increase visibility and promotion of recommendations")
        
        # Check ratings
        avg_effectiveness = rating_stats.get("average_effectiveness", 0)
        if avg_effectiveness < 3.0:
            recommendations.append("Review content quality and relevance")
        
        # Check engagement
        ctr = engagement_stats.get("click_through_rate", 0)
        if ctr < 0.5:
            recommendations.append("Improve recommendation titles and descriptions")
        
        return recommendations
    
    def _calculate_rating_distribution(self, ratings: List[float]) -> Dict[str, int]:
        """Calculate distribution of ratings"""
        if not ratings:
            return {}
        
        distribution = {str(i): 0 for i in range(1, 6)}
        
        for rating in ratings:
            if 1 <= rating <= 5:
                distribution[str(int(rating))] += 1
        
        return distribution
    
    async def _analyze_failure_patterns(
        self, 
        student_id: str, 
        failed_recommendations: List[str]
    ) -> Dict[str, Any]:
        """Analyze patterns in failed recommendations"""
        try:
            # Get data for failed recommendations
            failure_data = []
            
            for rec_id in failed_recommendations:
                # Get recommendation details
                rec_data = await self.db.recommendations.find_one({"recommendation_id": rec_id})
                if rec_data:
                    failure_data.append(rec_data)
            
            if not failure_data:
                return {}
            
            # Analyze patterns
            patterns = {
                "difficulty_too_high": False,
                "resource_type_mismatch": False,
                "learning_style_mismatch": False,
                "duration_too_long": False,
                "low_engagement": False
            }
            
            # Check difficulty patterns
            difficulty_levels = [rec.get("resource", {}).get("difficulty_level") for rec in failure_data]
            if difficulty_levels.count("advanced") > len(difficulty_levels) * 0.6:
                patterns["difficulty_too_high"] = True
            
            # Check duration patterns
            durations = [rec.get("resource", {}).get("estimated_duration", 0) for rec in failure_data]
            avg_duration = sum(durations) / len(durations) if durations else 0
            if avg_duration > 60:  # More than 1 hour
                patterns["duration_too_long"] = True
            
            # Infer preferences from successful recommendations
            successful_recs = await self._get_successful_recommendations(student_id)
            if successful_recs:
                successful_types = [rec.get("resource", {}).get("resource_type") for rec in successful_recs]
                failed_types = [rec.get("resource", {}).get("resource_type") for rec in failure_data]
                
                # Check if failed types are different from successful types
                if set(failed_types) != set(successful_types):
                    patterns["resource_type_mismatch"] = True
                    patterns["preferred_resource_types"] = list(set(successful_types))
                    patterns["avoided_types"] = list(set(failed_types) - set(successful_types))
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error analyzing failure patterns: {e}")
            return {}
    
    async def _get_successful_recommendations(self, student_id: str) -> List[Dict[str, Any]]:
        """Get successful recommendations for a student"""
        try:
            # Get completed recommendations with high ratings
            cursor = self.db.recommendation_feedback.find({
                "student_id": student_id,
                "completed": True,
                "effectiveness_rating": {"$gte": 4}
            })
            
            successful_feedback = await cursor.to_list(length=None)
            successful_rec_ids = [feedback["recommendation_id"] for feedback in successful_feedback]
            
            # Get recommendation details
            successful_recs = []
            for rec_id in successful_rec_ids:
                rec_data = await self.db.recommendations.find_one({"recommendation_id": rec_id})
                if rec_data:
                    successful_recs.append(rec_data)
            
            return successful_recs
            
        except Exception as e:
            logger.error(f"Error getting successful recommendations: {e}")
            return []