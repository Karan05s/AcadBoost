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
        Single aggregated query for performance
        """
        try:
            # Check Redis cache first
            cache_key = f"dashboard:{user_id}"
            cached_data = await redis_client.get(cache_key)
            
            if cached_data:
                return json.loads(cached_data)
            
            # Aggregate dashboard data from multiple collections
            pipeline = [
                {"$match": {"user_id": user_id}},
                {
                    "$lookup": {
                        "from": "learning_gaps",
                        "localField": "user_id",
                        "foreignField": "student_id",
                        "as": "gaps"
                    }
                },
                {
                    "$lookup": {
                        "from": "recommendations",
                        "localField": "user_id",
                        "foreignField": "student_id",
                        "as": "recommendations"
                    }
                },
                {
                    "$lookup": {
                        "from": "student_performance",
                        "localField": "user_id",
                        "foreignField": "student_id",
                        "as": "recent_performance"
                    }
                },
                {
                    "$project": {
                        "profile": {
                            "user_id": "$user_id",
                            "first_name": "$first_name",
                            "last_name": "$last_name",
                            "role": "$role",
                            "profile_completed": "$profile_completed",
                            "onboarding_completed": "$onboarding_completed"
                        },
                        "gaps_count": {"$size": "$gaps"},
                        "active_recommendations": {
                            "$size": {
                                "$filter": {
                                    "input": "$recommendations",
                                    "cond": {"$eq": ["$$this.completed", False]}
                                }
                            }
                        },
                        "recent_activity_count": {
                            "$size": {
                                "$filter": {
                                    "input": "$recent_performance",
                                    "cond": {
                                        "$gte": [
                                            "$$this.timestamp",
                                            {"$dateSubtract": {"startDate": "$$NOW", "unit": "day", "amount": 7}}
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            ]
            
            cursor = self.collection.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            
            dashboard_data = result[0] if result else {
                "profile": None,
                "gaps_count": 0,
                "active_recommendations": 0,
                "recent_activity_count": 0
            }
            
            # Cache for 5 minutes
            await redis_client.setex(cache_key, 300, json.dumps(dashboard_data, default=str))
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error getting dashboard data for user {user_id}: {e}")
            return {
                "profile": None,
                "gaps_count": 0,
                "active_recommendations": 0,
                "recent_activity_count": 0
            }
    
    async def clear_user_cache(self, user_id: str) -> None:
        """Clear user's cached data"""
        try:
            cache_keys = [
                f"dashboard:{user_id}",
                f"profile:{user_id}",
                f"recommendations:{user_id}"
            ]
            
            for key in cache_keys:
                await redis_client.delete(key)
                
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
            "progress": {
                "current_step": "profile_setup",
                "completed_steps": [],
                "total_steps": len(onboarding_steps),
                "progress_percentage": 0.0
            },
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