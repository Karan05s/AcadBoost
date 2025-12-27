"""
Notification Service
Handles achievement notifications, progress alerts, and alternative strategy suggestions
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.database import get_database
from app.core.redis_client import cache_manager
from app.models.user import NotificationPreferences
import logging
import asyncio

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notifications and alerts"""
    
    def __init__(self):
        self.notification_cache_ttl = 3600  # 1 hour cache
    
    async def generate_achievement_notifications(self, student_id: str) -> List[Dict[str, Any]]:
        """
        Generate achievement notifications for student
        Requirements: 5.3
        """
        try:
            db = await get_database()
            notifications = []
            
            # Check user notification preferences
            user_profile = await db.user_profiles.find_one({"user_id": student_id})
            if not user_profile:
                return notifications
            
            notification_prefs = user_profile.get("learning_preferences", {}).get("notification_preferences", {})
            if not notification_prefs.get("achievement_alerts", True):
                return notifications
            
            # Get recent achievements (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(days=1)
            
            # Check for new badges
            new_badges = await db.user_badges.find({
                "student_id": student_id,
                "earned_at": {"$gte": yesterday}
            }).to_list(length=None)
            
            for badge in new_badges:
                notifications.append({
                    "type": "achievement",
                    "subtype": "badge_earned",
                    "title": f"🏆 Badge Earned: {badge['name']}",
                    "message": badge["description"],
                    "priority": "high",
                    "created_at": badge["earned_at"],
                    "data": {
                        "badge_type": badge["badge_type"],
                        "icon": badge.get("icon", "🏆")
                    }
                })
            
            # Check for perfect scores
            perfect_scores = await db.student_performance.find({
                "student_id": student_id,
                "score": {"$gte": 0.95},
                "timestamp": {"$gte": yesterday}
            }).to_list(length=None)
            
            if perfect_scores:
                notifications.append({
                    "type": "achievement",
                    "subtype": "perfect_score",
                    "title": "🎯 Perfect Score Achievement!",
                    "message": f"Congratulations! You achieved {len(perfect_scores)} perfect score(s) today!",
                    "priority": "high",
                    "created_at": max(p["timestamp"] for p in perfect_scores),
                    "data": {
                        "count": len(perfect_scores),
                        "subjects": list(set(p.get("course_id", "Unknown") for p in perfect_scores))
                    }
                })
            
            # Check for improvement streaks
            streak_info = await self._check_improvement_streak(db, student_id)
            if streak_info["current_streak"] >= 3 and streak_info["is_new_milestone"]:
                notifications.append({
                    "type": "achievement",
                    "subtype": "improvement_streak",
                    "title": f"🔥 {streak_info['current_streak']}-Day Improvement Streak!",
                    "message": f"You're on fire! Keep up the great work with your {streak_info['current_streak']}-submission improvement streak!",
                    "priority": "medium",
                    "created_at": datetime.utcnow(),
                    "data": {
                        "streak_length": streak_info["current_streak"],
                        "streak_type": "improvement"
                    }
                })
            
            # Check for concept mastery
            newly_mastered = await self._check_newly_mastered_concepts(db, student_id)
            for concept in newly_mastered:
                notifications.append({
                    "type": "achievement",
                    "subtype": "concept_mastery",
                    "title": f"🎓 Concept Mastered: {concept['name']}",
                    "message": f"Excellent work! You've mastered {concept['name']} with {concept['mastery_level']:.1%} accuracy!",
                    "priority": "medium",
                    "created_at": datetime.utcnow(),
                    "data": {
                        "concept_id": concept["concept_id"],
                        "mastery_level": concept["mastery_level"]
                    }
                })
            
            return notifications
            
        except Exception as e:
            logger.error(f"Error generating achievement notifications for student {student_id}: {e}")
            return []
    
    async def generate_progress_milestone_alerts(self, student_id: str) -> List[Dict[str, Any]]:
        """
        Generate progress milestone alerts
        Requirements: 5.3
        """
        try:
            db = await get_database()
            alerts = []
            
            # Check user notification preferences
            user_profile = await db.user_profiles.find_one({"user_id": student_id})
            if not user_profile:
                return alerts
            
            notification_prefs = user_profile.get("learning_preferences", {}).get("notification_preferences", {})
            if not notification_prefs.get("achievement_alerts", True):
                return alerts
            
            # Check submission milestones
            total_submissions = await db.student_performance.count_documents({"student_id": student_id})
            submission_milestones = [10, 25, 50, 100, 250, 500, 1000]
            
            for milestone in submission_milestones:
                if total_submissions == milestone:
                    alerts.append({
                        "type": "milestone",
                        "subtype": "submissions",
                        "title": f"🎯 {milestone} Submissions Milestone!",
                        "message": f"Amazing dedication! You've completed {milestone} learning activities!",
                        "priority": "high",
                        "created_at": datetime.utcnow(),
                        "data": {
                            "milestone_type": "submissions",
                            "milestone_value": milestone
                        }
                    })
                    break
            
            # Check concept mastery milestones
            mastered_concepts = await db.learning_gaps.count_documents({
                "student_id": student_id,
                "gap_severity": {"$lt": 0.3}  # Low gap = high mastery
            })
            
            mastery_milestones = [5, 10, 20, 50, 100]
            for milestone in mastery_milestones:
                if mastered_concepts == milestone:
                    alerts.append({
                        "type": "milestone",
                        "subtype": "concept_mastery",
                        "title": f"🧠 {milestone} Concepts Mastered!",
                        "message": f"Incredible progress! You've mastered {milestone} learning concepts!",
                        "priority": "high",
                        "created_at": datetime.utcnow(),
                        "data": {
                            "milestone_type": "concept_mastery",
                            "milestone_value": milestone
                        }
                    })
                    break
            
            # Check weekly activity milestones
            week_ago = datetime.utcnow() - timedelta(days=7)
            weekly_submissions = await db.student_performance.count_documents({
                "student_id": student_id,
                "timestamp": {"$gte": week_ago}
            })
            
            if weekly_submissions >= 10:  # High activity week
                alerts.append({
                    "type": "milestone",
                    "subtype": "weekly_activity",
                    "title": "⚡ Super Active Week!",
                    "message": f"Outstanding effort! You completed {weekly_submissions} activities this week!",
                    "priority": "medium",
                    "created_at": datetime.utcnow(),
                    "data": {
                        "milestone_type": "weekly_activity",
                        "activity_count": weekly_submissions
                    }
                })
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error generating milestone alerts for student {student_id}: {e}")
            return []
    
    async def generate_alternative_strategy_suggestions(self, student_id: str) -> List[Dict[str, Any]]:
        """
        Generate alternative strategy suggestions for persistent gaps
        Requirements: 5.4
        """
        try:
            db = await get_database()
            suggestions = []
            
            # Find persistent learning gaps (gaps that haven't improved in 2+ weeks)
            two_weeks_ago = datetime.utcnow() - timedelta(days=14)
            
            persistent_gaps = await db.learning_gaps.find({
                "student_id": student_id,
                "gap_severity": {"$gte": 0.5},  # Significant gaps
                "last_updated": {"$lte": two_weeks_ago},  # No recent improvement
                "improvement_trend": {"$lte": 0.1}  # Little to no improvement
            }).to_list(length=None)
            
            for gap in persistent_gaps:
                concept_id = gap["concept_id"]
                gap_severity = gap["gap_severity"]
                
                # Get current recommendations for this gap
                current_recommendations = await db.recommendations.find({
                    "student_id": student_id,
                    "gap_id": gap["_id"],
                    "completed": False
                }).to_list(length=None)
                
                # Generate alternative strategies based on gap characteristics
                alternative_strategies = await self._generate_alternative_strategies(
                    db, student_id, concept_id, gap_severity, current_recommendations
                )
                
                if alternative_strategies:
                    suggestions.append({
                        "type": "strategy_suggestion",
                        "subtype": "persistent_gap",
                        "title": f"💡 New Learning Approach for {concept_id}",
                        "message": f"Let's try a different approach for {concept_id}. Here are some alternative strategies that might help!",
                        "priority": "medium",
                        "created_at": datetime.utcnow(),
                        "data": {
                            "concept_id": concept_id,
                            "gap_severity": gap_severity,
                            "alternative_strategies": alternative_strategies,
                            "gap_duration": (datetime.utcnow() - gap["last_updated"]).days
                        }
                    })
            
            # Check for learning style mismatch
            learning_style_suggestions = await self._check_learning_style_mismatch(db, student_id)
            suggestions.extend(learning_style_suggestions)
            
            # Check for study pattern suggestions
            study_pattern_suggestions = await self._generate_study_pattern_suggestions(db, student_id)
            suggestions.extend(study_pattern_suggestions)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating alternative strategy suggestions for student {student_id}: {e}")
            return []
    
    async def handle_notification_preferences(self, student_id: str, preferences: Dict[str, Any]) -> bool:
        """
        Update user notification preferences
        Requirements: 5.3
        """
        try:
            db = await get_database()
            
            # Update user profile with new notification preferences
            result = await db.user_profiles.update_one(
                {"user_id": student_id},
                {
                    "$set": {
                        "learning_preferences.notification_preferences": preferences,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Clear notification cache to force refresh
            cache_key = f"notifications:{student_id}"
            await cache_manager.delete_cache(cache_key)
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error updating notification preferences for student {student_id}: {e}")
            return False
    
    async def get_all_notifications(self, student_id: str) -> Dict[str, Any]:
        """Get all notifications for a student"""
        try:
            # Check cache first
            cache_key = f"notifications:{student_id}"
            cached_notifications = await cache_manager.get_cache(cache_key)
            
            if cached_notifications:
                return cached_notifications
            
            # Generate all notification types
            achievements = await self.generate_achievement_notifications(student_id)
            milestones = await self.generate_progress_milestone_alerts(student_id)
            suggestions = await self.generate_alternative_strategy_suggestions(student_id)
            
            # Combine and sort by priority and timestamp
            all_notifications = achievements + milestones + suggestions
            all_notifications.sort(key=lambda x: (
                {"high": 0, "medium": 1, "low": 2}[x["priority"]],
                -x["created_at"].timestamp()
            ))
            
            notifications_data = {
                "total_count": len(all_notifications),
                "unread_count": len(all_notifications),  # All are considered unread initially
                "notifications": all_notifications,
                "categories": {
                    "achievements": len(achievements),
                    "milestones": len(milestones),
                    "suggestions": len(suggestions)
                },
                "generated_at": datetime.utcnow()
            }
            
            # Cache for 1 hour
            await cache_manager.set_cache(cache_key, notifications_data, expire=self.notification_cache_ttl)
            
            return notifications_data
            
        except Exception as e:
            logger.error(f"Error getting notifications for student {student_id}: {e}")
            return {
                "total_count": 0,
                "unread_count": 0,
                "notifications": [],
                "categories": {"achievements": 0, "milestones": 0, "suggestions": 0},
                "generated_at": datetime.utcnow()
            }
    
    async def _check_improvement_streak(self, db: AsyncIOMotorDatabase, student_id: str) -> Dict[str, Any]:
        """Check for improvement streaks"""
        # Get recent performance data (last 10 submissions)
        recent_performance = await db.student_performance.find({
            "student_id": student_id
        }).sort("timestamp", -1).limit(10).to_list(length=None)
        
        if len(recent_performance) < 3:
            return {"current_streak": 0, "is_new_milestone": False}
        
        # Reverse to get chronological order
        recent_performance.reverse()
        
        current_streak = 0
        for i in range(1, len(recent_performance)):
            if recent_performance[i]["score"] > recent_performance[i-1]["score"]:
                current_streak += 1
            else:
                current_streak = 0
        
        # Check if this is a new milestone (3, 5, 7, 10+ submissions)
        milestone_streaks = [3, 5, 7, 10]
        is_new_milestone = current_streak in milestone_streaks
        
        return {
            "current_streak": current_streak,
            "is_new_milestone": is_new_milestone
        }
    
    async def _check_newly_mastered_concepts(self, db: AsyncIOMotorDatabase, student_id: str) -> List[Dict[str, Any]]:
        """Check for newly mastered concepts (last 24 hours)"""
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        # Find concepts that recently moved to mastered status
        newly_mastered = []
        
        # Get recent performance data to check for concept mastery
        recent_performance = await db.student_performance.find({
            "student_id": student_id,
            "timestamp": {"$gte": yesterday}
        }).to_list(length=None)
        
        # Group by concept and calculate mastery
        concept_performance = {}
        for submission in recent_performance:
            if "question_responses" in submission:
                for response in submission["question_responses"]:
                    concept_tags = response.get("concept_tags", [])
                    is_correct = response.get("correct", False)
                    
                    for concept in concept_tags:
                        if concept not in concept_performance:
                            concept_performance[concept] = {"correct": 0, "total": 0}
                        
                        concept_performance[concept]["total"] += 1
                        if is_correct:
                            concept_performance[concept]["correct"] += 1
        
        # Check for newly mastered concepts (>= 80% accuracy with at least 5 attempts)
        for concept, performance in concept_performance.items():
            if performance["total"] >= 5:
                mastery_level = performance["correct"] / performance["total"]
                if mastery_level >= 0.8:
                    # Check if this is a new mastery (wasn't mastered before yesterday)
                    old_performance = await db.student_performance.find({
                        "student_id": student_id,
                        "timestamp": {"$lt": yesterday},
                        "question_responses.concept_tags": concept
                    }).to_list(length=None)
                    
                    old_correct = 0
                    old_total = 0
                    for submission in old_performance:
                        for response in submission.get("question_responses", []):
                            if concept in response.get("concept_tags", []):
                                old_total += 1
                                if response.get("correct", False):
                                    old_correct += 1
                    
                    old_mastery = old_correct / old_total if old_total > 0 else 0
                    
                    # If old mastery was < 80% and new mastery is >= 80%, it's newly mastered
                    if old_mastery < 0.8:
                        newly_mastered.append({
                            "concept_id": concept,
                            "name": concept.replace("_", " ").title(),
                            "mastery_level": mastery_level,
                            "recent_attempts": performance["total"]
                        })
        
        return newly_mastered
    
    async def _generate_alternative_strategies(self, db: AsyncIOMotorDatabase, student_id: str, concept_id: str, gap_severity: float, current_recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate alternative learning strategies for persistent gaps"""
        strategies = []
        
        # Get user's learning preferences
        user_profile = await db.user_profiles.find_one({"user_id": student_id})
        learning_style = None
        if user_profile and user_profile.get("learning_preferences"):
            learning_style = user_profile["learning_preferences"].get("learning_style")
        
        # Get current resource types being used
        current_resource_types = {rec.get("resource_type") for rec in current_recommendations}
        
        # Suggest alternative resource types based on learning style
        if learning_style == "visual" and "video" not in current_resource_types:
            strategies.append({
                "type": "resource_change",
                "strategy": "visual_learning",
                "title": "Try Visual Learning Resources",
                "description": "Since you're a visual learner, try video tutorials and interactive diagrams for this concept.",
                "resource_types": ["video", "interactive", "diagram"]
            })
        
        if learning_style == "kinesthetic" and "practice" not in current_resource_types:
            strategies.append({
                "type": "resource_change",
                "strategy": "hands_on_practice",
                "title": "Hands-On Practice",
                "description": "Try more hands-on exercises and coding challenges to reinforce this concept.",
                "resource_types": ["practice", "exercise", "project"]
            })
        
        # Suggest study pattern changes
        if gap_severity > 0.7:  # High severity gaps
            strategies.append({
                "type": "study_pattern",
                "strategy": "spaced_repetition",
                "title": "Spaced Repetition Approach",
                "description": "Try reviewing this concept in shorter, more frequent sessions over several days.",
                "recommended_schedule": "15 minutes daily for 1 week"
            })
        
        # Suggest peer learning
        strategies.append({
            "type": "social_learning",
            "strategy": "peer_discussion",
            "title": "Peer Learning",
            "description": "Consider discussing this concept with classmates or joining a study group.",
            "action": "Find study partners or online communities"
        })
        
        # Suggest breaking down complex concepts
        if gap_severity > 0.6:
            strategies.append({
                "type": "concept_breakdown",
                "strategy": "prerequisite_review",
                "title": "Review Prerequisites",
                "description": "This concept might be challenging because of gaps in prerequisite knowledge. Let's review the fundamentals first.",
                "action": "Focus on foundational concepts first"
            })
        
        return strategies
    
    async def _check_learning_style_mismatch(self, db: AsyncIOMotorDatabase, student_id: str) -> List[Dict[str, Any]]:
        """Check if current resources match user's learning style"""
        suggestions = []
        
        try:
            # Get user's learning preferences
            user_profile = await db.user_profiles.find_one({"user_id": student_id})
            if not user_profile or not user_profile.get("learning_preferences"):
                return suggestions
            
            learning_style = user_profile["learning_preferences"].get("learning_style")
            if not learning_style:
                return suggestions
            
            # Get recent recommendations
            recent_recommendations = await db.recommendations.find({
                "student_id": student_id,
                "generated_at": {"$gte": datetime.utcnow() - timedelta(days=7)}
            }).to_list(length=None)
            
            if not recent_recommendations:
                return suggestions
            
            # Analyze resource type distribution
            resource_types = [rec.get("resource_type", "unknown") for rec in recent_recommendations]
            resource_distribution = {}
            for resource_type in resource_types:
                resource_distribution[resource_type] = resource_distribution.get(resource_type, 0) + 1
            
            # Check for learning style mismatch
            total_resources = len(resource_types)
            
            if learning_style == "visual":
                visual_resources = resource_distribution.get("video", 0) + resource_distribution.get("interactive", 0)
                if visual_resources / total_resources < 0.5:  # Less than 50% visual resources
                    suggestions.append({
                        "type": "learning_style_mismatch",
                        "subtype": "visual_learner",
                        "title": "🎨 More Visual Resources Available",
                        "message": "As a visual learner, you might benefit from more video and interactive content!",
                        "priority": "low",
                        "created_at": datetime.utcnow(),
                        "data": {
                            "learning_style": learning_style,
                            "current_visual_percentage": (visual_resources / total_resources) * 100,
                            "recommendation": "Request more visual learning materials"
                        }
                    })
            
            elif learning_style == "kinesthetic":
                practice_resources = resource_distribution.get("practice", 0) + resource_distribution.get("exercise", 0)
                if practice_resources / total_resources < 0.6:  # Less than 60% hands-on resources
                    suggestions.append({
                        "type": "learning_style_mismatch",
                        "subtype": "kinesthetic_learner",
                        "title": "🤹 More Hands-On Practice Available",
                        "message": "As a kinesthetic learner, you might learn better with more hands-on exercises!",
                        "priority": "low",
                        "created_at": datetime.utcnow(),
                        "data": {
                            "learning_style": learning_style,
                            "current_practice_percentage": (practice_resources / total_resources) * 100,
                            "recommendation": "Request more practical exercises and projects"
                        }
                    })
            
        except Exception as e:
            logger.error(f"Error checking learning style mismatch for student {student_id}: {e}")
        
        return suggestions
    
    async def _generate_study_pattern_suggestions(self, db: AsyncIOMotorDatabase, student_id: str) -> List[Dict[str, Any]]:
        """Generate study pattern suggestions based on performance data"""
        suggestions = []
        
        try:
            # Analyze study patterns from the last 2 weeks
            two_weeks_ago = datetime.utcnow() - timedelta(days=14)
            
            performance_data = await db.student_performance.find({
                "student_id": student_id,
                "timestamp": {"$gte": two_weeks_ago}
            }).sort("timestamp", 1).to_list(length=None)
            
            if len(performance_data) < 5:
                return suggestions
            
            # Analyze time-of-day patterns
            hour_performance = {}
            for submission in performance_data:
                hour = submission["timestamp"].hour
                if hour not in hour_performance:
                    hour_performance[hour] = {"scores": [], "count": 0}
                
                hour_performance[hour]["scores"].append(submission["score"])
                hour_performance[hour]["count"] += 1
            
            # Find best performing time periods
            best_hours = []
            for hour, data in hour_performance.items():
                if data["count"] >= 2:  # At least 2 submissions
                    avg_score = sum(data["scores"]) / len(data["scores"])
                    best_hours.append((hour, avg_score, data["count"]))
            
            best_hours.sort(key=lambda x: x[1], reverse=True)  # Sort by average score
            
            if best_hours and len(best_hours) >= 2:
                best_hour = best_hours[0][0]
                worst_hour = best_hours[-1][0]
                
                if best_hours[0][1] - best_hours[-1][1] > 0.2:  # Significant difference
                    time_period = self._get_time_period_name(best_hour)
                    suggestions.append({
                        "type": "study_pattern",
                        "subtype": "optimal_time",
                        "title": f"⏰ Your Peak Performance Time: {time_period}",
                        "message": f"You perform {((best_hours[0][1] - best_hours[-1][1]) * 100):.0f}% better during {time_period}. Consider scheduling important study sessions then!",
                        "priority": "low",
                        "created_at": datetime.utcnow(),
                        "data": {
                            "best_hour": best_hour,
                            "best_score": best_hours[0][1],
                            "worst_hour": worst_hour,
                            "worst_score": best_hours[-1][1],
                            "performance_difference": best_hours[0][1] - best_hours[-1][1]
                        }
                    })
            
            # Analyze session frequency patterns
            daily_submissions = {}
            for submission in performance_data:
                date_key = submission["timestamp"].date()
                if date_key not in daily_submissions:
                    daily_submissions[date_key] = {"count": 0, "scores": []}
                
                daily_submissions[date_key]["count"] += 1
                daily_submissions[date_key]["scores"].append(submission["score"])
            
            # Check if consistent daily practice leads to better performance
            consistent_days = [day for day, data in daily_submissions.items() if data["count"] >= 2]
            sporadic_days = [day for day, data in daily_submissions.items() if data["count"] == 1]
            
            if len(consistent_days) >= 3 and len(sporadic_days) >= 3:
                consistent_avg = sum(
                    sum(daily_submissions[day]["scores"]) / len(daily_submissions[day]["scores"])
                    for day in consistent_days
                ) / len(consistent_days)
                
                sporadic_avg = sum(
                    daily_submissions[day]["scores"][0] for day in sporadic_days
                ) / len(sporadic_days)
                
                if consistent_avg > sporadic_avg + 0.1:  # 10% better performance
                    suggestions.append({
                        "type": "study_pattern",
                        "subtype": "consistency",
                        "title": "📅 Consistency Pays Off!",
                        "message": f"Your performance is {((consistent_avg - sporadic_avg) * 100):.0f}% better on days with multiple study sessions. Try to maintain consistent daily practice!",
                        "priority": "low",
                        "created_at": datetime.utcnow(),
                        "data": {
                            "consistent_performance": consistent_avg,
                            "sporadic_performance": sporadic_avg,
                            "improvement_potential": consistent_avg - sporadic_avg
                        }
                    })
            
        except Exception as e:
            logger.error(f"Error generating study pattern suggestions for student {student_id}: {e}")
        
        return suggestions
    
    def _get_time_period_name(self, hour: int) -> str:
        """Convert hour to readable time period name"""
        if 6 <= hour < 12:
            return "Morning"
        elif 12 <= hour < 17:
            return "Afternoon"
        elif 17 <= hour < 21:
            return "Evening"
        else:
            return "Night"


# Create service instance
notification_service = NotificationService()