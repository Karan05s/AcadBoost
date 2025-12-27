"""
Analytics Pre-computation Service
Handles background processing of analytics data for optimized login performance
"""
import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.redis_client import cache_manager
from app.services.analytics_service import AnalyticsService
from app.services.recommendation_service import RecommendationService

logger = logging.getLogger(__name__)


class AnalyticsPrecomputeService:
    """Service for pre-computing analytics data in background"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.analytics_service = AnalyticsService(db)
        self.recommendation_service = RecommendationService(db)
    
    async def precompute_user_analytics(self, user_id: str) -> Dict[str, Any]:
        """
        Pre-compute analytics data for a specific user
        This runs in background to ensure fast login performance
        """
        try:
            logger.info(f"Starting analytics pre-computation for user {user_id}")
            
            # Get latest performance data
            performance_data = await self._get_recent_performance(user_id)
            
            # Compute learning gaps if we have performance data
            gaps_data = {}
            if performance_data:
                gaps_data = await self._compute_learning_gaps(user_id, performance_data)
            
            # Generate recommendations based on gaps
            recommendations_data = {}
            if gaps_data.get('gaps'):
                recommendations_data = await self._generate_recommendations(user_id, gaps_data['gaps'])
            
            # Compute progress trends
            progress_data = await self._compute_progress_trends(user_id)
            
            # Aggregate all pre-computed data
            precomputed_data = {
                "user_id": user_id,
                "performance_summary": performance_data,
                "learning_gaps": gaps_data,
                "recommendations": recommendations_data,
                "progress_trends": progress_data,
                "computed_at": datetime.utcnow().isoformat(),
                "cache_expires_at": (datetime.utcnow() + timedelta(minutes=30)).isoformat()
            }
            
            # Cache the pre-computed data
            await cache_manager.set_cache(
                f"precomputed_analytics:{user_id}",
                precomputed_data,
                expire=1800  # 30 minutes
            )
            
            logger.info(f"Completed analytics pre-computation for user {user_id}")
            return precomputed_data
            
        except Exception as e:
            logger.error(f"Error pre-computing analytics for user {user_id}: {e}")
            return {}
    
    async def _get_recent_performance(self, user_id: str) -> Dict[str, Any]:
        """Get recent performance data for user"""
        try:
            # Get performance data from last 30 days
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            pipeline = [
                {
                    "$match": {
                        "student_id": user_id,
                        "timestamp": {"$gte": cutoff_date}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_submissions": {"$sum": 1},
                        "avg_score": {"$avg": "$score"},
                        "max_score_possible": {"$avg": "$max_score"},
                        "recent_submissions": {"$push": "$$ROOT"}
                    }
                },
                {
                    "$project": {
                        "total_submissions": 1,
                        "avg_score": 1,
                        "max_score_possible": 1,
                        "performance_percentage": {
                            "$multiply": [
                                {"$divide": ["$avg_score", "$max_score_possible"]},
                                100
                            ]
                        },
                        "recent_activity": {
                            "$slice": [
                                {
                                    "$sortArray": {
                                        "input": "$recent_submissions",
                                        "sortBy": {"timestamp": -1}
                                    }
                                },
                                5
                            ]
                        }
                    }
                }
            ]
            
            cursor = self.db.student_performance.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            
            return result[0] if result else {
                "total_submissions": 0,
                "avg_score": 0,
                "performance_percentage": 0,
                "recent_activity": []
            }
            
        except Exception as e:
            logger.error(f"Error getting recent performance for user {user_id}: {e}")
            return {}
    
    async def _compute_learning_gaps(self, user_id: str, performance_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compute learning gaps based on performance data"""
        try:
            # Use analytics service to identify gaps
            gaps = await self.analytics_service.identify_learning_gaps(user_id)
            
            # Rank gaps by severity
            ranked_gaps = sorted(gaps, key=lambda x: x.get('gap_severity', 0), reverse=True)
            
            return {
                "total_gaps": len(gaps),
                "high_priority_gaps": len([g for g in gaps if g.get('gap_severity', 0) > 0.7]),
                "gaps": ranked_gaps[:10],  # Top 10 gaps
                "gap_categories": self._categorize_gaps(gaps)
            }
            
        except Exception as e:
            logger.error(f"Error computing learning gaps for user {user_id}: {e}")
            return {"total_gaps": 0, "gaps": []}
    
    async def _generate_recommendations(self, user_id: str, gaps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate recommendations based on learning gaps"""
        try:
            # Use recommendation service to generate recommendations
            recommendations = await self.recommendation_service.generate_recommendations(user_id)
            
            # Filter active recommendations
            active_recommendations = [r for r in recommendations if not r.get('completed', False)]
            
            # Prioritize by gap severity and user preferences
            prioritized_recommendations = sorted(
                active_recommendations,
                key=lambda x: x.get('priority_score', 0),
                reverse=True
            )
            
            return {
                "total_recommendations": len(recommendations),
                "active_recommendations": len(active_recommendations),
                "high_priority_recommendations": len([r for r in active_recommendations if r.get('priority_score', 0) > 0.8]),
                "recommendations": prioritized_recommendations[:5],  # Top 5 recommendations
                "recommendation_types": self._categorize_recommendations(active_recommendations)
            }
            
        except Exception as e:
            logger.error(f"Error generating recommendations for user {user_id}: {e}")
            return {"total_recommendations": 0, "recommendations": []}
    
    async def _compute_progress_trends(self, user_id: str) -> Dict[str, Any]:
        """Compute progress trends over time"""
        try:
            # Get performance data over last 90 days grouped by week
            cutoff_date = datetime.utcnow() - timedelta(days=90)
            
            pipeline = [
                {
                    "$match": {
                        "student_id": user_id,
                        "timestamp": {"$gte": cutoff_date}
                    }
                },
                {
                    "$group": {
                        "_id": {
                            "year": {"$year": "$timestamp"},
                            "week": {"$week": "$timestamp"}
                        },
                        "avg_score": {"$avg": "$score"},
                        "submission_count": {"$sum": 1},
                        "week_start": {"$min": "$timestamp"}
                    }
                },
                {
                    "$sort": {"week_start": 1}
                },
                {
                    "$project": {
                        "week_start": 1,
                        "avg_score": 1,
                        "submission_count": 1,
                        "performance_percentage": {
                            "$multiply": ["$avg_score", 10]  # Assuming max score is 10
                        }
                    }
                }
            ]
            
            cursor = self.db.student_performance.aggregate(pipeline)
            weekly_data = await cursor.to_list(length=None)
            
            # Calculate trend direction
            trend_direction = "stable"
            if len(weekly_data) >= 2:
                recent_avg = sum(w['performance_percentage'] for w in weekly_data[-3:]) / min(3, len(weekly_data))
                earlier_avg = sum(w['performance_percentage'] for w in weekly_data[:3]) / min(3, len(weekly_data))
                
                if recent_avg > earlier_avg + 5:
                    trend_direction = "improving"
                elif recent_avg < earlier_avg - 5:
                    trend_direction = "declining"
            
            return {
                "trend_direction": trend_direction,
                "weekly_data": weekly_data,
                "total_weeks_active": len(weekly_data),
                "current_streak": self._calculate_activity_streak(weekly_data)
            }
            
        except Exception as e:
            logger.error(f"Error computing progress trends for user {user_id}: {e}")
            return {"trend_direction": "stable", "weekly_data": []}
    
    def _categorize_gaps(self, gaps: List[Dict[str, Any]]) -> Dict[str, int]:
        """Categorize learning gaps by concept area"""
        categories = {}
        for gap in gaps:
            concept_id = gap.get('concept_id', 'unknown')
            # Extract category from concept_id (assuming format like 'math.algebra.linear_equations')
            category = concept_id.split('.')[0] if '.' in concept_id else concept_id
            categories[category] = categories.get(category, 0) + 1
        return categories
    
    def _categorize_recommendations(self, recommendations: List[Dict[str, Any]]) -> Dict[str, int]:
        """Categorize recommendations by resource type"""
        categories = {}
        for rec in recommendations:
            resource_type = rec.get('resource_type', 'unknown')
            categories[resource_type] = categories.get(resource_type, 0) + 1
        return categories
    
    def _calculate_activity_streak(self, weekly_data: List[Dict[str, Any]]) -> int:
        """Calculate current activity streak in weeks"""
        if not weekly_data:
            return 0
        
        streak = 0
        for week_data in reversed(weekly_data):
            if week_data.get('submission_count', 0) > 0:
                streak += 1
            else:
                break
        
        return streak
    
    async def schedule_precomputation(self, user_id: str, delay_seconds: int = 0) -> None:
        """Schedule analytics pre-computation for a user"""
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            
            await self.precompute_user_analytics(user_id)
            
        except Exception as e:
            logger.error(f"Error in scheduled pre-computation for user {user_id}: {e}")
    
    async def batch_precompute_analytics(self, user_ids: List[str]) -> Dict[str, Any]:
        """Pre-compute analytics for multiple users in batch"""
        results = {
            "successful": [],
            "failed": [],
            "total_processed": len(user_ids)
        }
        
        # Process users in batches to avoid overwhelming the system
        batch_size = 10
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i + batch_size]
            
            # Create tasks for concurrent processing
            tasks = [self.precompute_user_analytics(user_id) for user_id in batch]
            
            # Execute batch
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for j, result in enumerate(batch_results):
                user_id = batch[j]
                if isinstance(result, Exception):
                    results["failed"].append({"user_id": user_id, "error": str(result)})
                else:
                    results["successful"].append(user_id)
            
            # Small delay between batches
            if i + batch_size < len(user_ids):
                await asyncio.sleep(1)
        
        logger.info(f"Batch pre-computation completed: {len(results['successful'])} successful, {len(results['failed'])} failed")
        return results