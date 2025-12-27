"""
User Management Service
Handles user authentication, profiles, and onboarding
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.user import UserProfile, UserRole, LearningPreferences, AcademicInfo
from app.core.redis_client import redis_client, cache_manager
import logging
import json
import asyncio

logger = logging.getLogger(__name__)


class UserService:
    """User management service for authentication and profile management"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.user_profiles
    
    async def create_user_profile(
        self,
        user_id: str,
        email: str,
        username: str,
        first_name: str,
        last_name: str,
        role: UserRole,
        institution: Optional[str] = None
    ) -> UserProfile:
        """Create user profile in database"""
        
        # Create UserProfile object first to ensure email normalization
        profile = UserProfile(
            user_id=user_id,
            email=email,  # This will be normalized by Pydantic EmailStr
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role,
            institution=institution,
            created_at=datetime.utcnow(),
            last_login=None,
            email_verified=False,
            profile_completed=False,
            onboarding_completed=False,
            learning_preferences=None,
            academic_info=None
        )
        
        # Convert to dict for database storage (using normalized values)
        profile_data = {
            "user_id": profile.user_id,
            "email": profile.email,  # Use normalized email from Pydantic
            "username": profile.username,
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "role": profile.role.value,
            "institution": profile.institution,
            "created_at": profile.created_at,
            "last_login": profile.last_login,
            "email_verified": profile.email_verified,
            "profile_completed": profile.profile_completed,
            "onboarding_completed": profile.onboarding_completed,
            "learning_preferences": profile.learning_preferences,
            "academic_info": profile.academic_info
        }
        
        # Insert user profile
        result = await self.collection.insert_one(profile_data)
        profile_data["_id"] = result.inserted_id
        
        logger.info(f"Created user profile for user_id: {user_id}")
        return profile
    
    async def get_user_by_cognito_id(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile by Cognito user_id"""
        user_data = await self.collection.find_one({"user_id": user_id})
        
        if user_data:
            return UserProfile(**user_data)
        return None
    
    async def get_user_by_email(self, email: str) -> Optional[UserProfile]:
        """Get user profile by email"""
        user_data = await self.collection.find_one({"email": email})
        
        if user_data:
            return UserProfile(**user_data)
        return None
    
    async def update_last_login(self, user_id: str) -> bool:
        """Update user's last login timestamp"""
        result = await self.collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_login": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
    
    async def mark_email_verified(self, email: str) -> bool:
        """Mark user's email as verified"""
        result = await self.collection.update_one(
            {"email": email},
            {"$set": {"email_verified": True}}
        )
        
        return result.modified_count > 0
    
    async def update_profile(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        """Update user profile"""
        # Remove None values
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        if not update_data:
            return False
        
        result = await self.collection.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    async def get_dashboard_data(self, user_id: str) -> Dict[str, Any]:
        """
        Get optimized dashboard data for user login
        Uses pre-computed analytics when available, falls back to real-time computation
        """
        try:
            # First, check for pre-computed analytics data
            precomputed_data = await cache_manager.get_cache(f"precomputed_analytics:{user_id}")
            
            if precomputed_data:
                logger.info(f"Using pre-computed analytics for user {user_id}")
                return {
                    "source": "precomputed",
                    "computed_at": precomputed_data.get("computed_at"),
                    "performance_summary": precomputed_data.get("performance_summary", {}),
                    "learning_gaps": precomputed_data.get("learning_gaps", {}),
                    "recommendations": precomputed_data.get("recommendations", {}),
                    "progress_trends": precomputed_data.get("progress_trends", {})
                }
            
            # Fallback to cached dashboard data
            cache_key = f"dashboard:{user_id}"
            cached_data = await cache_manager.get_cache(cache_key)
            
            if cached_data:
                logger.info(f"Using cached dashboard data for user {user_id}")
                return cached_data
            
            # Last resort: real-time aggregated query (lightweight version)
            logger.info(f"Computing real-time dashboard data for user {user_id}")
            
            # Aggregate dashboard data from multiple collections (optimized)
            pipeline = [
                {"$match": {"user_id": user_id}},
                {
                    "$lookup": {
                        "from": "learning_gaps",
                        "localField": "user_id",
                        "foreignField": "student_id",
                        "as": "gaps",
                        "pipeline": [
                            {"$match": {"gap_severity": {"$gte": 0.5}}},  # Only significant gaps
                            {"$sort": {"gap_severity": -1}},
                            {"$limit": 5}
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
                            {"$limit": 3}
                        ]
                    }
                },
                {
                    "$lookup": {
                        "from": "student_performance",
                        "localField": "user_id",
                        "foreignField": "student_id",
                        "as": "recent_performance",
                        "pipeline": [
                            {
                                "$match": {
                                    "timestamp": {
                                        "$gte": datetime.utcnow() - timedelta(days=7)
                                    }
                                }
                            },
                            {"$sort": {"timestamp": -1}},
                            {"$limit": 5}
                        ]
                    }
                },
                {
                    "$project": {
                        "source": {"$literal": "realtime"},
                        "computed_at": {"$literal": datetime.utcnow().isoformat()},
                        "performance_summary": {
                            "recent_activity_count": {"$size": "$recent_performance"},
                            "avg_recent_score": {"$avg": "$recent_performance.score"}
                        },
                        "learning_gaps": {
                            "total_gaps": {"$size": "$gaps"},
                            "high_priority_gaps": {
                                "$size": {
                                    "$filter": {
                                        "input": "$gaps",
                                        "cond": {"$gte": ["$$this.gap_severity", 0.7]}
                                    }
                                }
                            }
                        },
                        "recommendations": {
                            "active_recommendations": {"$size": "$recommendations"},
                            "high_priority_recommendations": {
                                "$size": {
                                    "$filter": {
                                        "input": "$recommendations",
                                        "cond": {"$gte": ["$$this.priority_score", 0.8]}
                                    }
                                }
                            }
                        },
                        "progress_trends": {
                            "trend_direction": {"$literal": "stable"},
                            "recent_activity": "$recent_performance"
                        }
                    }
                }
            ]
            
            cursor = self.collection.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            
            dashboard_data = result[0] if result else {
                "source": "realtime",
                "computed_at": datetime.utcnow().isoformat(),
                "performance_summary": {
                    "recent_activity_count": 0,
                    "avg_recent_score": 0
                },
                "learning_gaps": {
                    "total_gaps": 0,
                    "high_priority_gaps": 0
                },
                "recommendations": {
                    "active_recommendations": 0,
                    "high_priority_recommendations": 0
                },
                "progress_trends": {
                    "trend_direction": "stable",
                    "recent_activity": []
                }
            }
            
            # Cache for 5 minutes
            await cache_manager.set_cache(cache_key, dashboard_data, expire=300)
            
            # Schedule background pre-computation for next time
            try:
                from app.services.analytics_precompute_service import AnalyticsPrecomputeService
                precompute_service = AnalyticsPrecomputeService(self.db)
                # Schedule with 30 second delay to not block login response
                asyncio.create_task(precompute_service.schedule_precomputation(user_id, delay_seconds=30))
            except Exception as e:
                logger.warning(f"Failed to schedule pre-computation for user {user_id}: {e}")
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error getting dashboard data for user {user_id}: {e}")
            return {
                "source": "error",
                "computed_at": datetime.utcnow().isoformat(),
                "performance_summary": {"recent_activity_count": 0, "avg_recent_score": 0},
                "learning_gaps": {"total_gaps": 0, "high_priority_gaps": 0},
                "recommendations": {"active_recommendations": 0, "high_priority_recommendations": 0},
                "progress_trends": {"trend_direction": "stable", "recent_activity": []}
            }
    
    async def clear_user_cache(self, user_id: str) -> None:
        """Clear user's cached data"""
        try:
            cache_keys = [
                f"dashboard:{user_id}",
                f"profile:{user_id}",
                f"recommendations:{user_id}",
                f"precomputed_analytics:{user_id}"
            ]
            
            for key in cache_keys:
                await cache_manager.delete_cache(key)
                
        except Exception as e:
            logger.error(f"Error clearing cache for user {user_id}: {e}")
    
    async def delete_user_profile(self, user_id: str) -> bool:
        """Delete user profile (for data deletion requests)"""
        result = await self.collection.delete_one({"user_id": user_id})
        
        if result.deleted_count > 0:
            # Clear cache
            await self.clear_user_cache(user_id)
            logger.info(f"Deleted user profile for user_id: {user_id}")
            return True
        
        return False
    
    # Onboarding Flow Methods
    
    async def initialize_onboarding(self, user_id: str) -> Dict[str, Any]:
        """Initialize onboarding process for a user"""
        
        # Define onboarding steps
        onboarding_steps = [
            "profile_setup",
            "preferences",
            "assessment", 
            "dashboard_setup"
        ]
        
        # Initialize onboarding data
        onboarding_data = {
            "user_id": user_id,
            "current_step": "profile_setup",
            "completed_steps": [],
            "total_steps": len(onboarding_steps),
            "progress_percentage": 0.0,
            "started_at": datetime.utcnow(),
            "step_data": {}
        }
        
        # Store in onboarding collection
        await self.db.user_onboarding.insert_one(onboarding_data)
        
        return {
            "current_step": "profile_setup",
            "completed_steps": [],
            "total_steps": len(onboarding_steps),
            "progress_percentage": 0.0,
            "next_action": "Please complete your profile information"
        }
    
    async def get_onboarding_progress(self, user_id: str) -> Dict[str, Any]:
        """Get current onboarding progress for a user"""
        
        onboarding_data = await self.db.user_onboarding.find_one({"user_id": user_id})
        
        if not onboarding_data:
            # Initialize if not exists
            return await self.initialize_onboarding(user_id)
        
        return {
            "current_step": onboarding_data["current_step"],
            "completed_steps": onboarding_data["completed_steps"],
            "total_steps": onboarding_data["total_steps"],
            "progress_percentage": onboarding_data["progress_percentage"]
        }
    
    async def complete_onboarding_step(self, user_id: str, step: str, step_data: Dict[str, Any]) -> bool:
        """Complete a specific onboarding step"""
        
        try:
            # Get current onboarding data
            onboarding_data = await self.db.user_onboarding.find_one({"user_id": user_id})
            
            if not onboarding_data:
                await self.initialize_onboarding(user_id)
                onboarding_data = await self.db.user_onboarding.find_one({"user_id": user_id})
            
            # Update completed steps
            completed_steps = onboarding_data.get("completed_steps", [])
            if step not in completed_steps:
                completed_steps.append(step)
            
            # Calculate progress
            total_steps = onboarding_data["total_steps"]
            progress_percentage = (len(completed_steps) / total_steps) * 100
            
            # Determine next step
            step_order = ["profile_setup", "preferences", "assessment", "dashboard_setup"]
            current_step_index = step_order.index(step) if step in step_order else 0
            next_step = step_order[current_step_index + 1] if current_step_index + 1 < len(step_order) else "completed"
            
            # Update onboarding data
            update_data = {
                "completed_steps": completed_steps,
                "progress_percentage": progress_percentage,
                "current_step": next_step,
                f"step_data.{step}": step_data,
                "updated_at": datetime.utcnow()
            }
            
            # Update onboarding collection
            await self.db.user_onboarding.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
            
            # Update user profile with step data
            profile_updates = {}
            
            if step == "preferences" and "learning_preferences" in step_data:
                profile_updates["learning_preferences"] = step_data["learning_preferences"]
            
            if step == "profile_setup":
                profile_updates.update(step_data)
                # Check if profile is now complete
                user_profile = await self.get_user_by_cognito_id(user_id)
                if user_profile and user_profile.first_name and user_profile.last_name:
                    profile_updates["profile_completed"] = True
            
            if step == "assessment" and "skill_level" in step_data:
                if "academic_info" not in profile_updates:
                    profile_updates["academic_info"] = {}
                profile_updates["academic_info"]["skill_level"] = step_data["skill_level"]
            
            if profile_updates:
                await self.update_profile(user_id, profile_updates)
            
            return True
            
        except Exception as e:
            logger.error(f"Error completing onboarding step {step} for user {user_id}: {e}")
            return False
    
    async def process_initial_assessment(self, user_id: str, assessment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process initial assessment and determine skill level"""
        
        try:
            questions = assessment_data.get("questions", [])
            answers = assessment_data.get("answers", [])
            
            # Simple scoring algorithm
            total_questions = len(questions)
            correct_answers = 0
            
            for i, answer in enumerate(answers):
                if i < len(questions):
                    question = questions[i]
                    if answer.get("answer") == question.get("correct_answer"):
                        correct_answers += 1
            
            # Determine skill level based on score
            score_percentage = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
            
            if score_percentage >= 80:
                skill_level = "advanced"
            elif score_percentage >= 60:
                skill_level = "intermediate"
            else:
                skill_level = "beginner"
            
            # Store assessment results
            assessment_result = {
                "total_questions": total_questions,
                "correct_answers": correct_answers,
                "score_percentage": score_percentage,
                "skill_level": skill_level,
                "completed_at": datetime.utcnow()
            }
            
            # Store in assessments collection
            await self.db.user_assessments.insert_one({
                "user_id": user_id,
                "assessment_type": "initial_onboarding",
                **assessment_result
            })
            
            return assessment_result
            
        except Exception as e:
            logger.error(f"Error processing initial assessment for user {user_id}: {e}")
            return {
                "skill_level": "beginner",
                "score_percentage": 0,
                "error": "Assessment processing failed"
            }
    
    async def complete_onboarding(self, user_id: str) -> bool:
        """Mark user onboarding as completed"""
        
        try:
            # Update user profile
            profile_update = await self.update_profile(user_id, {
                "onboarding_completed": True,
                "onboarding_completed_at": datetime.utcnow()
            })
            
            # Update onboarding record
            await self.db.user_onboarding.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "completed": True,
                        "completed_at": datetime.utcnow()
                    }
                }
            )
            
            return profile_update
            
        except Exception as e:
            logger.error(f"Error completing onboarding for user {user_id}: {e}")
            return False
    async def create_lti_user(
        self,
        email: str,
        name: Optional[str] = None,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
        roles: List[str] = None,
        lti_context: Optional[Dict[str, Any]] = None,
        deployment_id: Optional[str] = None
    ) -> UserProfile:
        """Create user from LTI launch data"""
        try:
            # Determine role from LTI roles
            user_role = UserRole.STUDENT  # Default
            if roles:
                if any("instructor" in role.lower() or "teacher" in role.lower() for role in roles):
                    user_role = UserRole.INSTRUCTOR
                elif any("admin" in role.lower() for role in roles):
                    user_role = UserRole.ADMIN
            
            # Generate username from email
            username = email.split("@")[0] if email else f"lti_user_{deployment_id}"
            
            # Parse names
            if not given_name and not family_name and name:
                name_parts = name.split(" ", 1)
                given_name = name_parts[0]
                family_name = name_parts[1] if len(name_parts) > 1 else ""
            
            # Create user profile
            profile = await self.create_user_profile(
                user_id=f"lti_{deployment_id}_{email}",
                email=email,
                username=username,
                first_name=given_name or "LTI",
                last_name=family_name or "User",
                role=user_role,
                institution=lti_context.get("label") if lti_context else None
            )
            
            # Store LTI context
            if lti_context:
                await self.db.lti_contexts.insert_one({
                    "user_id": profile.user_id,
                    "deployment_id": deployment_id,
                    "context": lti_context,
                    "created_at": datetime.utcnow()
                })
            
            logger.info(f"Created LTI user: {profile.user_id}")
            return profile
            
        except Exception as e:
            logger.error(f"Error creating LTI user: {e}")
            raise
    
    async def create_lti_session(
        self,
        user_id: str,
        lti_context: Optional[Dict[str, Any]] = None,
        resource_link: Optional[Dict[str, Any]] = None,
        deployment_id: Optional[str] = None
    ) -> str:
        """Create LTI session token"""
        try:
            import secrets
            session_token = secrets.token_urlsafe(32)
            
            # Store session
            await self.db.lti_sessions.insert_one({
                "session_token": session_token,
                "user_id": user_id,
                "lti_context": lti_context,
                "resource_link": resource_link,
                "deployment_id": deployment_id,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=8),
                "active": True
            })
            
            return session_token
            
        except Exception as e:
            logger.error(f"Error creating LTI session: {e}")
            raise
    
    async def update_course_enrollment(
        self,
        user_id: str,
        course_id: str,
        status: str = "enrolled"
    ):
        """Update user course enrollment"""
        try:
            # Update user profile with course enrollment
            await self.collection.update_one(
                {"user_id": user_id},
                {
                    "$addToSet": {"academic_info.enrolled_courses": course_id},
                    "$set": {"last_updated": datetime.utcnow()}
                }
            )
            
            # Store enrollment record
            await self.db.course_enrollments.update_one(
                {"user_id": user_id, "course_id": course_id},
                {
                    "$set": {
                        "user_id": user_id,
                        "course_id": course_id,
                        "status": status,
                        "enrolled_at": datetime.utcnow(),
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            logger.info(f"Updated course enrollment for user {user_id}: {course_id} ({status})")
            
        except Exception as e:
            logger.error(f"Error updating course enrollment: {e}")
            raise
    
    async def update_user_from_lms(self, user_id: str, updates: Dict[str, Any]):
        """Update user profile from LMS webhook data"""
        try:
            # Filter allowed updates
            allowed_fields = {
                "first_name", "last_name", "email", "institution"
            }
            
            filtered_updates = {
                k: v for k, v in updates.items() 
                if k in allowed_fields
            }
            
            if filtered_updates:
                filtered_updates["last_updated"] = datetime.utcnow()
                
                await self.collection.update_one(
                    {"user_id": user_id},
                    {"$set": filtered_updates}
                )
                
                logger.info(f"Updated user {user_id} from LMS: {list(filtered_updates.keys())}")
            
        except Exception as e:
            logger.error(f"Error updating user from LMS: {e}")
            raise