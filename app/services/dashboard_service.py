"""
Dashboard Data Aggregation Service
Handles optimized dashboard data queries, progress trends, and achievement detection
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.database import get_database
from app.core.redis_client import cache_manager
import logging
import asyncio

logger = logging.getLogger(__name__)


class DashboardService:
    """Service for dashboard data aggregation and progress tracking"""
    
    def __init__(self):
        self.cache_ttl = 300  # 5 minutes cache
    
    async def get_optimized_dashboard_data(self, student_id: str) -> Dict[str, Any]:
        """
        Get optimized dashboard data with progress trends and achievements
        Requirements: 5.1, 5.5
        """
        try:
            # Check cache first
            cache_key = f"dashboard_optimized:{student_id}"
            cached_data = await cache_manager.get_cache(cache_key)
            
            if cached_data:
                logger.info(f"Using cached dashboard data for student {student_id}")
                return cached_data
            
            db = await get_database()
            
            # Aggregate dashboard data with optimized queries
            dashboard_data = await self._aggregate_dashboard_data(db, student_id)
            
            # Calculate progress trends
            progress_trends = await self._calculate_progress_trends(db, student_id)
            dashboard_data["progress_trends"] = progress_trends
            
            # Detect achievements and milestones
            achievements = await self._detect_achievements(db, student_id)
            dashboard_data["achievements"] = achievements
            
            # Generate visual progress indicators
            visual_indicators = await self._generate_visual_indicators(db, student_id, progress_trends)
            dashboard_data["visual_indicators"] = visual_indicators
            
            # Cache the result
            await cache_manager.set_cache(cache_key, dashboard_data, expire=self.cache_ttl)
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error getting optimized dashboard data for student {student_id}: {e}")
            return self._get_fallback_dashboard_data(student_id)
    
    async def _aggregate_dashboard_data(self, db: AsyncIOMotorDatabase, student_id: str) -> Dict[str, Any]:
        """Aggregate core dashboard data using optimized queries"""
        
        # Single aggregation pipeline for multiple collections
        pipeline = [
            {"$match": {"user_id": student_id}},
            {
                "$lookup": {
                    "from": "student_performance",
                    "localField": "user_id",
                    "foreignField": "student_id",
                    "as": "performance_data",
                    "pipeline": [
                        {"$sort": {"timestamp": -1}},
                        {"$limit": 50}  # Last 50 submissions
                    ]
                }
            },
            {
                "$lookup": {
                    "from": "learning_gaps",
                    "localField": "user_id",
                    "foreignField": "student_id",
                    "as": "learning_gaps",
                    "pipeline": [
                        {"$match": {"gap_severity": {"$gte": 0.3}}},  # Only significant gaps
                        {"$sort": {"gap_severity": -1}},
                        {"$limit": 10}
                    ]
                }
            },
            {
                "$lookup": {
                    "from": "recommendations",
                    "localField": "user_id",
                    "foreignField": "student_id",
                    "as": "recommendations",
                    "pipeline": [
                        {"$match": {"completed": False}},
                        {"$sort": {"priority_score": -1}},
                        {"$limit": 5}
                    ]
                }
            },
            {
                "$project": {
                    "student_id": "$user_id",
                    "computed_at": {"$literal": datetime.utcnow()},
                    "performance_summary": {
                        "total_submissions": {"$size": "$performance_data"},
                        "avg_score": {"$avg": "$performance_data.score"},
                        "recent_avg_score": {
                            "$avg": {
                                "$slice": ["$performance_data.score", 10]  # Last 10 scores
                            }
                        },
                        "last_activity": {"$max": "$performance_data.timestamp"}
                    },
                    "learning_gaps_summary": {
                        "total_gaps": {"$size": "$learning_gaps"},
                        "critical_gaps": {
                            "$size": {
                                "$filter": {
                                    "input": "$learning_gaps",
                                    "cond": {"$gte": ["$$this.gap_severity", 0.7]}
                                }
                            }
                        },
                        "gaps_by_severity": "$learning_gaps"
                    },
                    "recommendations_summary": {
                        "active_recommendations": {"$size": "$recommendations"},
                        "high_priority_count": {
                            "$size": {
                                "$filter": {
                                    "input": "$recommendations",
                                    "cond": {"$gte": ["$$this.priority_score", 0.8]}
                                }
                            }
                        },
                        "recommendations": "$recommendations"
                    },
                    "raw_performance_data": "$performance_data"
                }
            }
        ]
        
        cursor = db.user_profiles.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        
        if result:
            return result[0]
        else:
            return {
                "student_id": student_id,
                "computed_at": datetime.utcnow(),
                "performance_summary": {
                    "total_submissions": 0,
                    "avg_score": 0.0,
                    "recent_avg_score": 0.0,
                    "last_activity": None
                },
                "learning_gaps_summary": {
                    "total_gaps": 0,
                    "critical_gaps": 0,
                    "gaps_by_severity": []
                },
                "recommendations_summary": {
                    "active_recommendations": 0,
                    "high_priority_count": 0,
                    "recommendations": []
                },
                "raw_performance_data": []
            }
    
    async def _calculate_progress_trends(self, db: AsyncIOMotorDatabase, student_id: str) -> Dict[str, Any]:
        """
        Calculate progress trend algorithms for visualization
        Requirements: 5.5
        """
        try:
            # Get performance data for the last 30 days
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            performance_cursor = db.student_performance.find({
                "student_id": student_id,
                "timestamp": {"$gte": thirty_days_ago}
            }).sort("timestamp", 1)
            
            performance_data = await performance_cursor.to_list(length=None)
            
            if not performance_data:
                return {
                    "trend_direction": "no_data",
                    "trend_strength": 0.0,
                    "weekly_progress": [],
                    "concept_progress": {},
                    "improvement_rate": 0.0
                }
            
            # Calculate weekly progress
            weekly_progress = self._calculate_weekly_progress(performance_data)
            
            # Calculate overall trend direction and strength
            trend_direction, trend_strength = self._calculate_trend_direction(performance_data)
            
            # Calculate concept-level progress
            concept_progress = await self._calculate_concept_progress(db, student_id, performance_data)
            
            # Calculate improvement rate
            improvement_rate = self._calculate_improvement_rate(performance_data)
            
            return {
                "trend_direction": trend_direction,  # "improving", "declining", "stable"
                "trend_strength": trend_strength,  # 0.0 to 1.0
                "weekly_progress": weekly_progress,
                "concept_progress": concept_progress,
                "improvement_rate": improvement_rate,
                "data_points": len(performance_data),
                "period_start": thirty_days_ago,
                "period_end": datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error calculating progress trends for student {student_id}: {e}")
            return {
                "trend_direction": "error",
                "trend_strength": 0.0,
                "weekly_progress": [],
                "concept_progress": {},
                "improvement_rate": 0.0
            }
    
    def _calculate_weekly_progress(self, performance_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate weekly progress aggregation"""
        weekly_data = {}
        
        for submission in performance_data:
            # Get week start date
            submission_date = submission["timestamp"]
            week_start = submission_date - timedelta(days=submission_date.weekday())
            week_key = week_start.strftime("%Y-%W")
            
            if week_key not in weekly_data:
                weekly_data[week_key] = {
                    "week_start": week_start,
                    "scores": [],
                    "submission_count": 0
                }
            
            weekly_data[week_key]["scores"].append(submission["score"])
            weekly_data[week_key]["submission_count"] += 1
        
        # Calculate weekly averages
        weekly_progress = []
        for week_key, data in sorted(weekly_data.items()):
            avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            weekly_progress.append({
                "week": week_key,
                "week_start": data["week_start"],
                "avg_score": avg_score,
                "submission_count": data["submission_count"]
            })
        
        return weekly_progress
    
    def _calculate_trend_direction(self, performance_data: List[Dict[str, Any]]) -> tuple[str, float]:
        """Calculate overall trend direction and strength"""
        if len(performance_data) < 3:
            return "insufficient_data", 0.0
        
        # Split data into first and second half
        mid_point = len(performance_data) // 2
        first_half = performance_data[:mid_point]
        second_half = performance_data[mid_point:]
        
        first_half_avg = sum(s["score"] for s in first_half) / len(first_half)
        second_half_avg = sum(s["score"] for s in second_half) / len(second_half)
        
        difference = second_half_avg - first_half_avg
        
        # Determine trend direction
        if abs(difference) < 0.05:  # Less than 5% change
            trend_direction = "stable"
        elif difference > 0:
            trend_direction = "improving"
        else:
            trend_direction = "declining"
        
        # Calculate trend strength (0.0 to 1.0)
        max_possible_change = 1.0  # Assuming scores are normalized 0-1
        trend_strength = min(abs(difference) / max_possible_change, 1.0)
        
        return trend_direction, trend_strength
    
    async def _calculate_concept_progress(self, db: AsyncIOMotorDatabase, student_id: str, performance_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate progress by concept/topic"""
        concept_scores = {}
        
        for submission in performance_data:
            if "question_responses" in submission:
                for response in submission["question_responses"]:
                    concept_tags = response.get("concept_tags", [])
                    is_correct = response.get("correct", False)
                    
                    for concept in concept_tags:
                        if concept not in concept_scores:
                            concept_scores[concept] = {"correct": 0, "total": 0}
                        
                        concept_scores[concept]["total"] += 1
                        if is_correct:
                            concept_scores[concept]["correct"] += 1
        
        # Calculate concept mastery levels
        concept_progress = {}
        for concept, scores in concept_scores.items():
            mastery_level = scores["correct"] / scores["total"] if scores["total"] > 0 else 0
            concept_progress[concept] = {
                "mastery_level": mastery_level,
                "total_attempts": scores["total"],
                "correct_attempts": scores["correct"],
                "status": self._get_mastery_status(mastery_level)
            }
        
        return concept_progress
    
    def _get_mastery_status(self, mastery_level: float) -> str:
        """Get mastery status based on level"""
        if mastery_level >= 0.8:
            return "mastered"
        elif mastery_level >= 0.6:
            return "proficient"
        elif mastery_level >= 0.4:
            return "developing"
        else:
            return "needs_work"
    
    def _calculate_improvement_rate(self, performance_data: List[Dict[str, Any]]) -> float:
        """Calculate rate of improvement over time"""
        if len(performance_data) < 5:
            return 0.0
        
        # Use linear regression to calculate improvement rate
        scores = [s["score"] for s in performance_data]
        n = len(scores)
        
        # Simple linear regression
        x_sum = sum(range(n))
        y_sum = sum(scores)
        xy_sum = sum(i * scores[i] for i in range(n))
        x_squared_sum = sum(i * i for i in range(n))
        
        # Calculate slope (improvement rate)
        slope = (n * xy_sum - x_sum * y_sum) / (n * x_squared_sum - x_sum * x_sum)
        
        return slope
    
    async def _detect_achievements(self, db: AsyncIOMotorDatabase, student_id: str) -> Dict[str, Any]:
        """
        Detect achievement milestones for the student
        Requirements: 5.1
        """
        try:
            achievements = {
                "recent_achievements": [],
                "milestone_progress": {},
                "badges_earned": [],
                "streaks": {}
            }
            
            # Check for recent achievements (last 7 days)
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            
            # Get recent performance data
            recent_performance = await db.student_performance.find({
                "student_id": student_id,
                "timestamp": {"$gte": seven_days_ago}
            }).sort("timestamp", -1).to_list(length=None)
            
            # Detect perfect score achievements
            perfect_scores = [p for p in recent_performance if p.get("score", 0) >= 0.95]
            if perfect_scores:
                achievements["recent_achievements"].append({
                    "type": "perfect_score",
                    "count": len(perfect_scores),
                    "description": f"Achieved {len(perfect_scores)} perfect scores this week!",
                    "earned_at": max(p["timestamp"] for p in perfect_scores)
                })
            
            # Detect improvement streaks
            streak_info = self._detect_improvement_streak(recent_performance)
            if streak_info["current_streak"] >= 3:
                achievements["streaks"]["improvement"] = streak_info
                achievements["recent_achievements"].append({
                    "type": "improvement_streak",
                    "count": streak_info["current_streak"],
                    "description": f"On a {streak_info['current_streak']}-submission improvement streak!",
                    "earned_at": datetime.utcnow()
                })
            
            # Check milestone progress
            milestones = await self._check_milestone_progress(db, student_id)
            achievements["milestone_progress"] = milestones
            
            # Check for newly earned badges
            badges = await self._check_earned_badges(db, student_id)
            achievements["badges_earned"] = badges
            
            return achievements
            
        except Exception as e:
            logger.error(f"Error detecting achievements for student {student_id}: {e}")
            return {
                "recent_achievements": [],
                "milestone_progress": {},
                "badges_earned": [],
                "streaks": {}
            }
    
    def _detect_improvement_streak(self, performance_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect consecutive improvement in scores"""
        if len(performance_data) < 2:
            return {"current_streak": 0, "best_streak": 0}
        
        # Sort by timestamp (oldest first for streak calculation)
        sorted_data = sorted(performance_data, key=lambda x: x["timestamp"])
        
        current_streak = 0
        best_streak = 0
        
        for i in range(1, len(sorted_data)):
            if sorted_data[i]["score"] > sorted_data[i-1]["score"]:
                current_streak += 1
                best_streak = max(best_streak, current_streak)
            else:
                current_streak = 0
        
        return {
            "current_streak": current_streak,
            "best_streak": best_streak,
            "total_submissions": len(sorted_data)
        }
    
    async def _check_milestone_progress(self, db: AsyncIOMotorDatabase, student_id: str) -> Dict[str, Any]:
        """Check progress towards learning milestones"""
        milestones = {}
        
        # Total submissions milestone
        total_submissions = await db.student_performance.count_documents({"student_id": student_id})
        milestones["total_submissions"] = {
            "current": total_submissions,
            "next_milestone": self._get_next_submission_milestone(total_submissions),
            "progress_percentage": self._calculate_milestone_progress(total_submissions, "submissions")
        }
        
        # Concept mastery milestone
        mastery_count = await db.learning_gaps.count_documents({
            "student_id": student_id,
            "gap_severity": {"$lt": 0.3}  # Low gap severity = high mastery
        })
        milestones["concepts_mastered"] = {
            "current": mastery_count,
            "next_milestone": self._get_next_mastery_milestone(mastery_count),
            "progress_percentage": self._calculate_milestone_progress(mastery_count, "mastery")
        }
        
        return milestones
    
    def _get_next_submission_milestone(self, current: int) -> int:
        """Get next submission milestone"""
        milestones = [10, 25, 50, 100, 250, 500, 1000]
        for milestone in milestones:
            if current < milestone:
                return milestone
        return current + 100  # Beyond predefined milestones
    
    def _get_next_mastery_milestone(self, current: int) -> int:
        """Get next mastery milestone"""
        milestones = [5, 10, 20, 50, 100]
        for milestone in milestones:
            if current < milestone:
                return milestone
        return current + 10  # Beyond predefined milestones
    
    def _calculate_milestone_progress(self, current: int, milestone_type: str) -> float:
        """Calculate progress percentage towards next milestone"""
        if milestone_type == "submissions":
            next_milestone = self._get_next_submission_milestone(current)
        else:
            next_milestone = self._get_next_mastery_milestone(current)
        
        if next_milestone == current:
            return 100.0
        
        # Find previous milestone
        if milestone_type == "submissions":
            milestones = [0, 10, 25, 50, 100, 250, 500, 1000]
        else:
            milestones = [0, 5, 10, 20, 50, 100]
        
        prev_milestone = 0
        for milestone in milestones:
            if milestone < next_milestone:
                prev_milestone = milestone
            else:
                break
        
        progress = (current - prev_milestone) / (next_milestone - prev_milestone) * 100
        return min(progress, 100.0)
    
    async def _check_earned_badges(self, db: AsyncIOMotorDatabase, student_id: str) -> List[Dict[str, Any]]:
        """Check for newly earned badges"""
        badges = []
        
        # Check if badges collection exists and get existing badges
        existing_badges = await db.user_badges.find({"student_id": student_id}).to_list(length=None)
        existing_badge_types = {badge["badge_type"] for badge in existing_badges}
        
        # Check for "First Perfect Score" badge
        if "first_perfect" not in existing_badge_types:
            perfect_score = await db.student_performance.find_one({
                "student_id": student_id,
                "score": {"$gte": 0.95}
            })
            if perfect_score:
                badges.append({
                    "badge_type": "first_perfect",
                    "name": "Perfect Score",
                    "description": "Achieved your first perfect score!",
                    "earned_at": datetime.utcnow(),
                    "icon": "🏆"
                })
        
        # Check for "Consistent Learner" badge (5+ submissions in a week)
        if "consistent_learner" not in existing_badge_types:
            week_ago = datetime.utcnow() - timedelta(days=7)
            weekly_submissions = await db.student_performance.count_documents({
                "student_id": student_id,
                "timestamp": {"$gte": week_ago}
            })
            if weekly_submissions >= 5:
                badges.append({
                    "badge_type": "consistent_learner",
                    "name": "Consistent Learner",
                    "description": "Completed 5+ activities this week!",
                    "earned_at": datetime.utcnow(),
                    "icon": "📚"
                })
        
        # Store new badges in database
        if badges:
            for badge in badges:
                badge["student_id"] = student_id
                await db.user_badges.insert_one(badge)
        
        return badges
    
    async def _generate_visual_indicators(self, db: AsyncIOMotorDatabase, student_id: str, progress_trends: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate visual progress indicators for dashboard
        Requirements: 5.5
        """
        try:
            indicators = {
                "progress_chart_data": [],
                "concept_mastery_chart": {},
                "achievement_timeline": [],
                "performance_heatmap": {},
                "trend_indicators": {}
            }
            
            # Generate progress chart data (last 30 days)
            if progress_trends.get("weekly_progress"):
                indicators["progress_chart_data"] = [
                    {
                        "date": week["week_start"].isoformat(),
                        "score": week["avg_score"],
                        "submissions": week["submission_count"]
                    }
                    for week in progress_trends["weekly_progress"]
                ]
            
            # Generate concept mastery chart
            if progress_trends.get("concept_progress"):
                indicators["concept_mastery_chart"] = {
                    concept: {
                        "mastery_percentage": data["mastery_level"] * 100,
                        "status": data["status"],
                        "attempts": data["total_attempts"]
                    }
                    for concept, data in progress_trends["concept_progress"].items()
                }
            
            # Generate trend indicators
            indicators["trend_indicators"] = {
                "direction": progress_trends.get("trend_direction", "stable"),
                "strength": progress_trends.get("trend_strength", 0.0),
                "improvement_rate": progress_trends.get("improvement_rate", 0.0),
                "color": self._get_trend_color(progress_trends.get("trend_direction", "stable")),
                "icon": self._get_trend_icon(progress_trends.get("trend_direction", "stable"))
            }
            
            # Generate performance heatmap data (daily activity)
            heatmap_data = await self._generate_performance_heatmap(db, student_id)
            indicators["performance_heatmap"] = heatmap_data
            
            return indicators
            
        except Exception as e:
            logger.error(f"Error generating visual indicators for student {student_id}: {e}")
            return {
                "progress_chart_data": [],
                "concept_mastery_chart": {},
                "achievement_timeline": [],
                "performance_heatmap": {},
                "trend_indicators": {}
            }
    
    def _get_trend_color(self, trend_direction: str) -> str:
        """Get color for trend indicator"""
        color_map = {
            "improving": "#22c55e",  # Green
            "declining": "#ef4444",  # Red
            "stable": "#6b7280",     # Gray
            "no_data": "#9ca3af",    # Light gray
            "error": "#f59e0b"       # Orange
        }
        return color_map.get(trend_direction, "#6b7280")
    
    def _get_trend_icon(self, trend_direction: str) -> str:
        """Get icon for trend indicator"""
        icon_map = {
            "improving": "📈",
            "declining": "📉",
            "stable": "➡️",
            "no_data": "❓",
            "error": "⚠️"
        }
        return icon_map.get(trend_direction, "➡️")
    
    async def _generate_performance_heatmap(self, db: AsyncIOMotorDatabase, student_id: str) -> Dict[str, Any]:
        """Generate performance heatmap for the last 90 days"""
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)
        
        # Get daily performance data
        pipeline = [
            {
                "$match": {
                    "student_id": student_id,
                    "timestamp": {"$gte": ninety_days_ago}
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$timestamp"
                        }
                    },
                    "avg_score": {"$avg": "$score"},
                    "submission_count": {"$sum": 1}
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        
        cursor = db.student_performance.aggregate(pipeline)
        daily_data = await cursor.to_list(length=None)
        
        heatmap_data = {}
        for day in daily_data:
            heatmap_data[day["_id"]] = {
                "score": day["avg_score"],
                "submissions": day["submission_count"],
                "intensity": min(day["submission_count"] / 5.0, 1.0)  # Normalize to 0-1
            }
        
        return heatmap_data
    
    def _get_fallback_dashboard_data(self, student_id: str) -> Dict[str, Any]:
        """Return fallback data when main query fails"""
        return {
            "student_id": student_id,
            "computed_at": datetime.utcnow(),
            "status": "fallback",
            "performance_summary": {
                "total_submissions": 0,
                "avg_score": 0.0,
                "recent_avg_score": 0.0,
                "last_activity": None
            },
            "learning_gaps_summary": {
                "total_gaps": 0,
                "critical_gaps": 0,
                "gaps_by_severity": []
            },
            "recommendations_summary": {
                "active_recommendations": 0,
                "high_priority_count": 0,
                "recommendations": []
            },
            "progress_trends": {
                "trend_direction": "no_data",
                "trend_strength": 0.0,
                "weekly_progress": [],
                "concept_progress": {},
                "improvement_rate": 0.0
            },
            "achievements": {
                "recent_achievements": [],
                "milestone_progress": {},
                "badges_earned": [],
                "streaks": {}
            },
            "visual_indicators": {
                "progress_chart_data": [],
                "concept_mastery_chart": {},
                "achievement_timeline": [],
                "performance_heatmap": {},
                "trend_indicators": {}
            }
        }


# Create service instance
dashboard_service = DashboardService()